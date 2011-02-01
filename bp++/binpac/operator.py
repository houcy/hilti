# $Id$
"""
Overloading operators for BinPAC++ types.
-----------------------------------------

To overload an operator, you define a new class with methods to implement the
functionality. The class is decorated with the operator it is overloading and
the expression types it applies to.

For example, the following class overloads the plus-operator for expressions
of integer type::

    from operators import *
    from core.type import integer

    @operator.plus(type.Integer, type.Integer)
    class Plus:
        def type(expr1, expr2):
            # Result type of expression.
            return type.Integer()

        def codegen(expr1, expr2):
            [... generate HILTI code ...]


Once defined, the BinPAC++ compiler will call `codegen` to generate HILTI code
for all sums integer expressions. Likewise, it will call ``type` when it needs
to know the result type of evaluating the operators. While these two methods
are mandatory, there are further optional methods can be added to the class as
needed; see below.

The definition of the class must be located inside a submodule of the BinPAC++
`pactypes` package, and it's recommended to group the classes by the types
they support (e.g., putting all integer operators intp a subpackage
`packtypes.integer`.).

Class decorators
================

There is one decorator for each operator provided by the BinPAC++ language.
The arguments for decorator are instances of ~~type.Type, corresponding to the
types of expressions the overloaded operator applies to. The number of types
is specific to each operator.  The matching of expression type to operators is
performed via Python's `isinstance` and thus inheritance relatioships might be
exploited by specifiying a base class in the decorator's arguments.

The following operators are available:

XXX include auto-generated text

Class methods for operators
===========================

A class decorated with @operator.* may provide the following methods. Most of
them receive instances of ~~Expression objects as arguments, with the number
determined by the operator type.  Note these methods do not receive a *self*
attribute; they are all class methods.

.. function:: resolve(resolver, <exprs>)

  Optional. Adds additional resolving functionality performed *after* it has
  already been determined that the operator applies.

  resolver: ~~Resolver - The resolver to use.

.. function:: validate(vld, <exprs>)

  Optional. Adds additional validation functionality performed *after* it has
  already been determined that the operator applies.

  vld: ~~Validator - The validator to use.

.. function:: simplify(<exprs>)

  Optional. Implements simplifactions of the operator, such as constant
  folding.

  The argument expressions passed will be already be simplified.

  Returns: ~~expr - A new expression object representing a simplified version
  of the operator to be used instead; or None if it can't be simplified into
  something else.

.. function:: type(<exprs>)

  Mandatory. Returns the result type this operator evaluates the operands to.

  Returns: ~~type.Type - An type *instance* defining the result type.

.. function:: evaluate(cg, <exprs>)

  Mandatory. Implements evaluation of the operator, generating the
  corresponding HILTI code.

  *cg*: ~~CodeGen - The current code generator.

  Returns: ~~hilti.instructin.Operand - An operand with the
  value of the evaluated expression.

.. function:: assign(cg, <exprs>, rhs)

  Optional. Implements assignment, generating the corresponding HILTI code.
  If not implemented, it is assumed that the operator doesn't allow
  assignment. The ``<exprs>`` are interpreted just as with ~~evaluate;
  ``rhs`` is the right-hand side value to assign (as a ~~hilti.operand.Operand).

  *cg*: ~~CodeGen - The current code generator.

.. function:: coerceCtorTo(const, dsttype):

   Optional. Applies only to the ~~Coerce operator. Coerces a ctor of the
   operator's type to another type. This may or may not be possible; if not,
   the method must throw a ~~CoerceError.

   *ctor*: ~~expression.Ctor - The ctor expression to coerce.

   *dsttype*: ~~Type - The type to coerce the constant into.

   Returns: ~~expression.Ctor - A ctor of *dsttype* with the coerceed value.

   Throws: ~~CoerceError if the coerce is not possible. There's no need to augment
   the exception with an explaining string as that will be added automatically.

.. function:: coerceTo(cg, expr, dsttype):

   Optional. Applies only to the ~~Coerce operator. Coerces a non-constant
   expression of the operator's type to another type.

   *cg*: ~~CodeGen - The current code generator.
   *expr*: ~~Expression - The expression to coerce.
   *dsttype*: ~~Type - The type to coerce the expression into.

   Returns: ~~Expression - A new expression of the target type with
   the coerceed expression.

.. todo:: Not sure where this should go, but note somewhere that the Cast
   operator does not need to deal with things the Coerce operator already
   does. Coercion will always be tried first for a cast, and if that works,
   we're done.

.. todo:: The implementation of overloaded operators in ``operator.py`` has
   become quite messy. This file needs a significant cleanup.

"""

import sys
import inspect
import functools

import type as mod_type
import expr

import binpac.util as util

import hilti

### Available operators and operator methods.

def _pacUnary(op):
    def _pac(printer, exprs):
        printer.output(op)
        exprs[0].pac(printer)

    return _pac

def _pacUnaryPostfix(op):
    def _pac(printer, exprs):
        printer.output(op)
        exprs[0].pac(printer)

    return _pac

def _pacBinary(op):
    def _pac(printer, exprs):
        exprs[0].pac(printer)
        printer.output(op)
        exprs[1].pac(printer)

    return _pac

def _pacEnclosed(op):
    def _pac(printer, exprs):
        printer.output(op)
        exprs[0].pac(printer)
        printer.output(op)

    return _pac

def _pacMethodCall(printer, exprs):
    exprs[0].pac(printer)
    printer.output(".%s" % exprs[1])
    printer.output("(")

    args = exprs[2]

    for i in range(len(args)):
        args[i].pac(printer)
        if i != len(args) - 1:
            printer.output(",")

    printer.output(")")

def _pacCall(printer, exprs):
    exprs[0].pac(printer)
    printer.output("(")

    args = exprs[1]

    for i in range(len(args)):
        args[i].pac(printer)
        if i != len(args) - 1:
            printer.output(",")

    printer.output(")")

_Operators = {
    # Operator name, #operands, description.
    "Plus": (2, "The sum of two expressions. (`a + b`)", _pacBinary("+")),
    "Minus": (2, "The difference of two expressions. (`a - b`)", _pacBinary("-")),
    "Mult": (2, "The product of two expressions. (`a * b`)", _pacBinary("*")),
    "Div": (2, "The division of two expressions. (`a / b`)", _pacBinary("*")),
    "Mod": (2, "The modulo operation for two expressions. (`a % b`)", _pacBinary("%")),
    "Neg": (1, "The negation of an expressions. (`- a`)", _pacUnary("-")),
    "Coerce": (2, "Coerces an expression into another type.", lambda p, e: p.output("<Coerce>")),
    "Attribute": (2, "Attribute expression. (`a.b`)", _pacBinary(".")),
    "HasAttribute": (2, "Has-attribute expression. (`a?.b`)", _pacBinary("?.")),
    "Call": (1, "Function call. (`a()`)", _pacCall),
    "MethodCall": (3, "Method call. (`a.b()`)", _pacMethodCall),
    "Size": (1, "The size of an expression's value, with type-defined definition of \"size\" (`|a|`)", _pacUnary("|")),
    "Equal": (2, "Compares two values whether they are equal. (``a == b``)", _pacBinary("==")),
    "LogicalAnd": (2, "Logical 'and' of boolean values. (``a && b``)", _pacBinary("&&")),
    "LogicalOr": (2, "Logical 'or' of boolean values. (``a || b``)", _pacBinary("||")),
    "BitAnd": (2, "Bitwise 'and' of integer values. (``a & b``)", _pacBinary("&")),
    "BitOr": (2, "Bitwise 'or' of integer values. (``a | b``)", _pacBinary("|")),
    "BitXor": (2, "Bitwise 'xor' of integer values. (``a | b``)", _pacBinary("^")),
    "ShiftLeft": (2, "Bitwise shift right for integer values. (``a << b``)", _pacBinary("<<")),
    "ShiftRight": (2, "Bitwise shift left for integer values. (``a >> b``)", _pacBinary(">>")),
    "Power": (2, "Raising to a power (``a ** b``)", _pacBinary("**")),
    "PlusAssign": (2, "Adds to an operand in place (`` a += b``)", _pacBinary("+=")),
    "Lower": (2, "Lower than comparision. (``a < b``)", _pacBinary("<")),
    "Greater": (2, "Greater than comparision. (``a > b``)", _pacBinary(">")),
    "IncrPrefix": (1, "Prefix increment operator (`++i`)", _pacUnary("++")),
    "DecrPrefix": (1, "Prefix decrement operator (`--i`)", _pacUnary("--")),
    "IncrPostfix": (1, "Postfix increment operator (`i++`)", _pacUnaryPostfix("++")),
    "DecrPostfix": (1, "Postfix decrement operator (`i--`)", _pacUnaryPostfix("--")),
    "Deref": (1, "Dereference operator. (`*i`)", _pacUnary("*")),
    "Index": (2, "Element at a given index (`a[i]`).", lambda p, e: p.output("<Index>")),
    "New": (1, "Allocate a new instance of a type (`new T`).", _pacUnary("new")),
    "Cast": (1, "Explictly cast into another type.", lambda p, e: p.output("<Cast>")),
    }

_Methods = ["resolve", "validate", "simplify", "evaluate", "assign", "type",
            "coerceTo", "coerceCtorTo", "typeCoerceTo"]

### Public functions.

def hasOperator(op, exprs):
    """Returns True if there's an overloaded operator for a set of operands.

    op: ~~Operator - The operator.
    exprs: list of ~~Expression - The expressions for the operator.

    Returns: bool - True if there's an operator found implementing
    that method.
    """
    func = _findOp("*", op, exprs)
    return func != None

def resolve(op, resolver, exprs):
    """Resolves an operator's arguments.

    op: ~~Operator - The operator.
    resolver: ~~Resolver - The resolver to use.
    exprs: list of ~~Expression - The expressions for the operator.
    """
    func = _findOp("resolve", op, exprs)
    if not func:
        # No validate function defined means ok.
        return None

    return func(resolver, *exprs)

def validate(op, vld, exprs):
    """Validates an operator's arguments.

    op: ~~Operator - The operator.
    vld: ~~Validator - The validator to use.
    exprs: list of ~~Expression - The expressions for the operator.
    """
    func = _findOp("validate", op, exprs)
    if not func:
        # No validate function defined means ok.
        return None

    return func(vld, *exprs)

def simplify(op, exprs):
    """Simplifies an operator.

    op: ~~Operator - The operator.
    exprs: list of ~~Expression - The expressions for the operator. They are
    expected to already be simplified.

    Returns: ~~expr - A new expression, representing the simplified operator
    to be used instead; or None if the operator could not be simplified.
    """
    func = _findOp("simplify", op, exprs)
    result = func(*exprs) if func else None

    assert (not result) or isinstance(result, expr.Ctor)
    return result

def evaluate(op, cg, exprs):
    """Generates HILTI code for an expression.

    op: string - The name of the operator.
    *cg*: ~~CodeGen - The current code generator.

    exprs: list of ~~Expression - The expressions for the operator.

    Returns: ~~hilti.instructin.Operand - An operand with the value of
    the evaluated expression.
    """
    func = _findOp("evaluate", op, exprs)

    if not func:
        util.error("no evaluate implementation for %s operator with %s" % (op, _fmtArgTypes(exprs)))

    return func(cg, *exprs)

def assign(op, cg, exprs, rhs):
    """Generates HILTI code for an assignment.

    op: string - The name of the operator.
    *cg*: ~~CodeGen - The current code generator.

    exprs: list of ~~Expression - The expressions for the operator.

    rhs: ~~hilti.operand.Operand - The right-hand side to assign.
    """
    func = _findOp("assign", op, exprs)

    if not func:
        util.error("no assign implementation for %s operator with %s" % (op, _fmtArgTypes(exprs)))

    func(cg, *(exprs + [rhs]))

def type(op, exprs):
    """Returns the result type for an operator.

    op: string - The name of the operator.
    exprs: list of ~~Expression - The expressions for the operator.

    Returns: ~~type.Type - The result type.
    """
    func = _findOp("type", op, exprs)

    if not func:
        args = _fmtArgTypes(exprs)
        util.error("no type implementation for %s operator with expression types %s" % (op, args), context=exprs[0].location())

    return func(*exprs)

class CoerceError(Exception):
    pass

def canCoerceExprTo(e, dsttype):
    if e.type() == dsttype:
        return True

    if isinstance(e, expr.Ctor):
        return _findOp("coerceCtorTo", Operator.Coerce, [e, dsttype])
    else:
        return _findOp("coerceTo", Operator.Coerce, [e, dsttype])

def canCoerceTo(srctype, dsttype):
    """Returns whether an expression of the given type (assumed to be
    non-constant) can be coerced to a given target type. If *dsttype* is of
    the same type as the expression, the result is always True.

    *srctype*: ~~Type - The source type.
    *dstype*: ~~Type - The target type.

    Returns: bool - True if the expression can be coerceed.
    """
    if srctype == dsttype:
        return True

    if _findOp("coerceTo", Operator.Coerce, [srctype, dsttype]):
        return True

    return False

def coerceExprTo(cg, e, dsttype):
    """Coerces an expression (assumed to be non-constant) of one type into
    another. This operator must only be called if ~~canCoerceExprTo indicates
    that the coerce is supported.

    *cg*: ~~CodeGen - The current code generator.
    e: ~~expr - The expression to coerce.
    dsttype: ~~Type - The type to coerce the expression into.

    Returns: ~~Expression - A new expression of the target type with the
    coerceed expression.
    """

    assert canCoerceExprTo(e, dsttype)

    if e.type() == dsttype:
        return e

    func = _findOp("coerceTo", Operator.Coerce, [e, dsttype])
    assert func != None
    result = func(cg, e, dsttype)

    if isinstance(result, hilti.operand.Operand):
        result = expr.Hilti(result, dsttype)

    return result

def coerceCtorTo(e, dsttype):
    """Coerces a ctor expression of one type into another. This may or may
    not be possible; if not, a ~~CoerceError is thrown.

    const: ~~expression.Ctor - The ctor expression to coerce.
    dsttype: ~~Type - The type to coerce the constant into.

    Returns: ~~expression.Ctor - A new ctor expression of the target type
    with the coerceed value.

    Throws: ~~CoerceError if the coerce is not possible.
    """
    if e.type() == dsttype:
        return e

    func = _findOp("coerceCtorTo", Operator.Coerce, [e, dsttype])
    if not func:
        raise CoerceError

    assert e.isInit()
    return expr.Ctor(func(e.value(), dsttype), dsttype)

class Operator:
    """Constants defining the available operators."""
    # Note: we add the constants dynamically to this class' namespace, see
    # below.
    pass

def generateDecoratorDoc(file):
    """Generates documentation for the available operator decorators. The
    documentation will be included into the developer manual.

    file: file - The filo into which the output will be written.
    """
    for (op, vals) in _Operators.items().sorted():
        (exprs, descr, pac) = vals
        exprs = ", ".join(["type"] * exprs)
        print >>file, ".. function @operator.%s(%s)" % (op, exprs)
        print >>file
        print >>file, "   %s" % descr
        print >>file

def pacOperator(printer, op, exprs):
    """Converts an operator into parseable BinPAC++ code.

    printer: ~~Printer - The printer to use.
    op: string - The name of the operator; use the operator.Operator.*
    constants here.
    exprs: list of ~Expression - The operator's operands.
    """
    vals = _Operators[op]
    (num, descr, pac) = vals
    pac(printer, exprs)

### Internal code for keeping track of registered operators.

_OverloadTable = {}

def _registerOperator(operator, f, exprs):
    try:
        _OverloadTable[operator] += [(f, exprs)]
    except KeyError:
        _OverloadTable[operator] = [(f, exprs)]

def _fmtTypes(types):
    return ",".join([str(t) for t in types])

def _fmtOneArgType(a):

    if isinstance(a, list):
        return '(' + ", ".join([_fmtOneArgType(x) for x in a]) + ')'

    if isinstance(a, mod_type.Type):
        return str(a)

    if isinstance(a.type(), mod_type.Type):
        return str(a.type())

    return str(a)

def _fmtArgTypes(exprs):
    return " and ".join([_fmtOneArgType(a) for a in exprs])

def _makeOp(op, *exprs):
    def __makeOp(cls):
        for m in _Methods:
            if m in cls.__dict__:
                f = cls.__dict__[m]
                #if len(inspect.getexprspec(f)[0]) != len(exprs):
                #    util.internal_error("%s has wrong number of argument for %s" % (m, _fmtTypes(exprs)))

                _registerOperator((op, m), f, exprs)
                _registerOperator((op, "*"), f, exprs)

        return cls

    return __makeOp

class _Decorators:
    def __init__(self):
        for (op, vals) in _Operators.items():
            (exprs, descr, pac) = vals
            globals()[op] = functools.partial(_makeOp, op)

class Mutable:
    def __init__(self, arg):
        self._arg = arg

class Optional:
    def __init__(self, arg):
        self._arg = arg

class Any:
    pass

class Match:
    pass

class NoMatch:
    pass

def _makeCoerce(func, dst):
    def _coerce(*args):
        if not args[0]:
            args = args[1:] # Strip dummy cg argument.

        args = (list(args) + [dst])
        result = func(*args)

        if isinstance(result, hilti.operand.Operand):
            result = expr.Hilti(result, dst)

        return result

    return _coerce

def _matchOneTypeClass(ty, proto, try_coercion, have_cg):
    rc = isinstance(ty, proto)

    if rc:
        return (rc, None)

    if not try_coercion:
        return (False, None)

    # See if we can coerce the type to what we need.
    method = "coerceTo" if have_cg else "typeCoerceTo"
    coerce = _findOp(method, Operator.Coerce, [ty, proto])
    if not coerce:
        return (False, None)

    return (True, _makeCoerce(coerce, proto))

def _matchOneTypeInstance(ty, proto, try_coercion, have_cg):
    rc = (ty == proto)

    if rc:
        return (rc, None)

    if not try_coercion:
        return (False, None)

    # See if we can coerce the type to what we need.
    coerce = _findOp("coerceTo", Operator.Coerce, [ty, proto])
    if not coerce:
        return (False, None)

    return (False, _makeCoerce(coerce, proto))

def _matchType(arg, proto, all, try_coercion, have_cg):

    if inspect.isfunction(proto):
        proto = proto(all)

    # Note: arg can be a type or and expression, or a list/tuple of those.

    if isinstance(arg, list) and isinstance(proto, list):
        if len(arg) == 0 and len(proto) == 0:
            return (True, None)

    if inspect.isclass(proto) and proto == Match:
        return (True, None)

    if inspect.isclass(proto) and proto == NoMatch:
        return (False, None)

    if isinstance(proto, Any):
        return (True, None)

    if isinstance(proto, Optional):
        if not arg:
            return (True, None)
        else:
            proto = proto._arg

    if not arg:
        return (False, None)

    if isinstance(proto, list) or isinstance(proto, tuple):
        if not (isinstance(arg, list) or isinstance(arg, tuple)):
            return (False, None)

        if len(proto) < len(arg):
            return (False, None)

        arg = arg + [None] * (len(proto) - len(arg))

        new_args = []

        for (e, p) in zip(arg, proto):
            (rc, a) = _matchType(e, p, all, try_coercion, have_cg)
            if not rc:
                return (False, None)

        new_args += [a]

        return (True, new_args)

    mutable = False

    if isinstance(proto, Mutable):
        mutable = True
        proto = proto._arg

    if inspect.isclass(arg):
        if inspect.isclass(proto):
            rc = (arg == proto)
            return (rc, None)

        rc = isinstance(proto, arg)
        return (rc, None)

    if isinstance(arg, expr.Expression) and isinstance(proto, expr.Expression):
        rc = (arg == proto)
        return (rc, None)

    ty = arg if isinstance(arg, mod_type.Type) else arg.type()
    init = arg.isInit() if isinstance(arg, expr.Expression) else False

    assert isinstance(ty, mod_type.Type)

    if inspect.isclass(proto):
        if mutable and init:
            return (rc, None)

        return _matchOneTypeClass(ty, proto, try_coercion, have_cg)

    if isinstance(proto, mod_type.Type):
        if mutable and init:
            return (rc, None)

        return _matchOneTypeInstance(ty, proto, try_coercion, have_cg)

    assert False and "Is this ever reached? If so, when?"
    rc = (ty == proto)

    return (rc, None)

# A function object that remebers which coercions need to be
# applied to its arguments.
class _CoercingCall:
    def __init__(self, op, funcs):
        self._op = op
        self._funcs = funcs if funcs else []

    def __call__(self, *args):
        # Apply coercion functions.
        funcs = []
        i = 0
        for a in args:
            if isinstance(a, expr.Expression) and i < len(self._funcs):
                funcs += [self._funcs[i]]
                i += 1
            else:
                funcs += [None]

        if len(args) and not isinstance(args[0], expr.Expression):
            cg = args[0]
        else:
            cg = None

        new_args = self._coerce(args, funcs, cg)

        return self._op(*new_args)

    def _coerce(self, arg, func, cg):
        if isinstance(arg, tuple) or isinstance(arg, list):
            new_args = []
            for (a, f) in zip(arg, func):

                if f == None:
                    new_args += [a]

                else:
                    if cg:
                        new_args += [self._coerce(a, f, cg)]
                    else:
                        new_args += [self._coerce(a, f, cg)]

            return new_args

        if not func:
            return arg

        return func(cg, arg)

def _findOp(method, op, args):
    assert method == "*" or method in _Methods

    # Args can be expressions or types here.

    util.check_class(op, str, "_findOp (use Operator.*)")

    try:
        ops = _OverloadTable[(op, method)]
    except KeyError:
        return None

    matches = []

    # Two rounds, first without coercion to find the best match, then with.
    for try_coercion in (False, True):

        for (func, proto) in ops:

            if len(proto) < len(args):
                continue

            args = [e for e in args] + [None] * (len(proto) - len(args))

            new_args = []

            for (a, t) in zip(args, proto):
                (rc, na) = _matchType(a, t, args, try_coercion, (method == "evaluate"))
                if not rc:
                    break

                new_args += [na]
            else:
                matches += [(func, proto, new_args)]

        if matches:
            break

        if op == Operator.Coerce:
            # Don't even try recursive coercion.
            break

    if not matches:
        return None

    if method == "*":
        return True

    if len(matches) == 1:
        return _CoercingCall(matches[0][0], matches[0][2]) if op != Operator.Coerce else matches[0][0]

    msg = "ambigious operator definitions: types %s match\n" % _fmtArgTypes(args)
    for (func, proto) in matches:
        msg += "    %s\n" % _fmtTypes(proto)

    util.internal_error(msg)

### Initialization code.

# Create "operator" namespace.
operator = _Decorators()

# Add operator constants to class Operators.
for (op, vals) in _Operators.items():
    (exprs, descr, pac) = vals
    Operator.__dict__[op] = op
    # FIXME: Can't change the docstring here. What to do?
    # op.__doc = descr

