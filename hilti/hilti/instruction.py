# $Id$

builtin_type = type
builtin_id = id

import constant
import node
import operand
import type

class Instruction(node.Node):
    """Base class for all instructions supported by the HILTI language.
    
    To create a new instruction do however *not* derive directly from
    Instruction but use the ~~instruction decorator.
    
    op1: ~~Operand - The instruction's first operand, or None if unused.
    op2: ~~Operand - The instruction's second operand, or None if unused.
    op3: ~~Operand - The instruction's third operand, or None if unused.
    target: ~~ID - The instruction's target, or None if unused.
    location: ~~Location - A location to be associated with the instruction. 
    """
    
    _signature = None
    
    def __init__(self, op1=None, op2=None, op3=None, target=None, location=None):
        assert not target or isinstance(target, operand.ID) or isinstance(target, operand.LLVM)
        
        super(Instruction, self).__init__(location)
        self._op1 = op1
        self._op2 = op2
        self._op3 = op3
        self._target = target
        self._location = location
        
        cb = self.signature().callback()
        if cb:
            cb(self)

    def signature(self):
        """Returns the instruction's signature.
        
        Returns: ~~Signature - The signature.
        """
        return self.__class__._signature
            
    def name(self):
        """Returns the instruction's name. The name is the mnemonic as used in
        a HILTI program.
        
        Returns: string - The name.
        """
        return self.signature().name()
        
    def op1(self):
        """Returns the instruction's first operand.
        
        Returns: ~~Operand - The operand, or None if unused.
        """
        return self._op1
    
    def op2(self):
        """Returns the instruction's second operand.
        
        Returns: ~~Operand - The operand, or None if unused.
        """
        return self._op2
    
    def op3(self):
        """Returns the instruction's third operand.
        
        Returns: ~~Operand - The operand, or None if unused.
        """
        return self._op3

    def target(self):
        """Returns the instruction's target.
        
        Returns: ~~ID - The target, or None if unused.
        """
        return self._target

    def setOp1(self, op):
        """Sets the instruction's first operand.
        
        op: ~~Operand - The new operand to set.
        """
        self._op1 = op
        
    def setOp2(self, op):
        """Sets the instruction's second operand.
        
        op: ~~Operand - The new operand to set.
        """
        self._op2 = op
    
    def setOp3(self, op):
        """Sets the instruction's third operand.
        
        op: ~~Operand - The new operand to set.
        """
        self._op3 = op
        
    def setTarget(self, target):
        """Sets the instruction's target.
        
        op: ~~ID - The new operand to set.
        """
        assert not target or isinstance(target, operand.ID)
        self._target = target
        
    def __str__(self):
        target = "(%s) = " % self._target if self._target else ""
        op1 = " (%s)" % self._op1 if self._op1 else ""
        op2 = " (%s)" % self._op2 if self._op2 else ""
        op3 = " (%s)" % self._op3 if self._op3 else ""
        return "%s%s%s%s%s" % (target, self.signature().name(), op1, op2, op3)

    ### Overridden from Node.
    
    def resolve(self, resolver):
        for op in (self._op1, self._op2, self._op3, self._target):
            if op:
                op.resolve(resolver)
                
    def validate(self, vld):
        errors = vld.errors()
        
        for op in (self._op1, self._op2, self._op3, self._target):
            if op:
                op.validate(vld)
        
        (success, errormsg) = self._signature.matchWithInstruction(self)
        if not success:
            vld.error(self, errormsg)
            return

        if self._target and not isinstance(self._target, operand.ID):
            vld.error(self, "target must be an identifier")
            
    def output(self, printer):
        printer.printComment(self, separate=True)
        
        if self._target:
            self._target.output(printer)
            printer.output(" = ")
            
        printer.output(self.name())
        
        for op in (self._op1, self._op2, self._op3):
            if op:
                printer.output(" ")
                op.output(printer)

        printer.output("", nl=True)
                
    def canonify(self, canonifier):
        for op in (self._op1, self._op2, self._op3, self._target):
            if op:
                op.canonify(canonifier)
            
    def codegen(self, cg):
        cg.trace("%s" % self)
    
    # Visitor support.
    def visit(self, visitor):
        visitor.visitPre(self)

        for op in (self._op1, self._op2, self._op3, self._target):
            if op:
                op.visit(visitor)

        visitor.visitPost(self)

class Operator(Instruction):
    """Class for instructions that are overloaded by their operands' types.
    While most HILTI instructions are tied to a particular type, *operators*
    are generic instructions that can operator on different types.
    
    To create a new operator do *not* derive directly from Operator but use
    the ~~operator decorator.
    
    op1: ~~Operand - The operator's first operand, or None if unused.
    op2: ~~Operand - The operator's second operand, or None if unused.
    op3: ~~Operand - The operator's third operand, or None if unused.
    target: ~~ID - The operator's target, or None if unused.
    location: ~~Location - A location to be associated with the operator. 
    """
    def __init__(self, op1=None, op2=None, op3=None, target=None, location=None):
        super(Operator, self).__init__(op1, op2, op3, target, location)

    ### Overridden from Node.

    def validate(self, vld):    
        Instruction.validate(self, vld)
        
        ops = _findOverloadedOperator(self)
        
        if len(ops) == 0:
            vld.error(self, "no matching implementation of overloaded operator found")
    
        if len(ops) > 1:
            vld.error(self,  "use of overloaded operator is ambigious, multiple matching implementations found:")
        
        self._callOps(ops, "validate", vld)
                
    def resolve(self, resolver):
        Instruction.resolve(self, resolver)
        ops = _findOverloadedOperator(self)
        if ops:
            self._callOps(ops, "resolve", resolver)

    def canonify(self, canonifier):
        Instruction.canonify(self, canonifier)
        ops = _findOverloadedOperator(self)
        assert ops
        self._callOps(ops, "canonify", canonifier)
                
    def codegen(self, cg):
        Instruction.codegen(self, cg)
        ops = _findOverloadedOperator(self)
        assert ops
        self._callOps(ops, "codegen", cg)
        
    ### Private.
    
    def _callOps(self, ops, method, arg):
        for o in ops:
            try:
                # We can't call o.resolve() here directly as that recurse
                # infinitly if the class doesn't override the implementation of
                # the method. 
                o.__class__.__dict__[method](o, arg)
            except KeyError:
                pass
            
from signature import *
    
def _make_ins_init(myclass):
    def ins_init(self, op1=None, op2=None, op3=None, target=None, location=None):
        super(self.__class__, self).__init__(op1, op2, op3, target, location)
        
    ins_init.myclass = myclass
    return ins_init

def instruction(name, op1=None, op2=None, op3=None, target=None, callback=None, terminator=False, location=None):
    """A *decorater* for classes derived from ~~Instruction. The decorator
    defines the new instruction's ~~Signature. The arguments correpond to
    those of the ~~Signature constructor."""
    def register(ins):
        global _Instructions
        ins._signature = Signature(name, op1, op2, op3, target, callback, terminator)
        d = dict(ins.__dict__)
        d["__init__"] = _make_ins_init(ins)
        newclass = builtin_type(ins.__name__, (ins.__base__,), d)
        _Instructions[name] = newclass
        return newclass
    
    return register

# Currently, "operator" is just an alias for "instruction".
operator = instruction
"""A *decorater* for classes derived from ~~Operator. The decorator
defines the new operators's ~~Signature. The arguments correpond to
those of the ~~Signature constructor."""

def overload(operator, op1, op2=None, op3=None, target=None):
    """A *decorater* for classes that provide type-specific overloading of an
    operator. The decorator defines the overloaded operator's ~~Signature. The
    arguments correpond to those of the ~~Signature constructor except for
    *operator* which must be a subclass of ~~Operator."""
    def register(ins):
        global _OverloadedOperators
        assert issubclass(operator, Operator)

        global _Instructions
        ins._signature = Signature(operator().name(), op1, op2, op3, target)
        d = dict(ins.__dict__)
        d["__init__"] = _make_ins_init(ins)
        newclass = builtin_type(ins.__name__, (ins.__base__,), d)
        
        idx = operator.__name__
        try:
            _OverloadedOperators[idx] += [ins]
        except:
            _OverloadedOperators[idx] = [ins]
            
        return newclass
    
    return register

_Instructions = {}    
_OverloadedOperators = {}

def getInstructions():
    """Returns a dictionary of instructions. More precisely, the function
    returns all classes decorated with either ~~instruction or ~~operator;
    these classes will be derived from ~~Instruction and represent a complete
    enumeration of all instructions provided by the HILTI language. The
    dictionary is indexed by the instruction name and maps the name to the
    ~~Instruction instance.
    
    Returns: dictionary of ~~Instruction-derived classes - The list of all
    instructions.
    """
    return _Instructions

def createInstruction(name, op1=None, op2=None, op3=None, target=None, location=None):
    """Instantiates a new instruction. 
    
    name: The name of the instruction to be instantiated; i.e., the mnemnonic
    as defined by a ~~instruction decorator.
    
    op1: ~~Operand - The instruction's first operand, or None if unused.
    op2: ~~Operand - The instruction's second operand, or None if unused.
    op3: ~~Operand - The instruction's third operand, or None if unused.
    target: ~~ID - The instruction's target, or None if unused.
    location: ~~Location - A location to be associated with the instruction. 
    """
    try:
        i = _Instructions[name](op1, op2, op3, target, location)
    except KeyError:
        return None

    return i

def _findOverloadedOperator(op):
    """Returns the type-specific version(s) of an overloaded operator. Based on
    an instance of ~~Operator, it will search all type-specific
    implementations (i.e., all ~~OverloadedOperators) and return the matching
    ones. 
    
    op: ~~Operator - The operator for which to return the type-specific version.
    
    Returns: list of ~~OverloadedOperator - The list of matching operater
    implementations.
    """
    
    matches = []

    try:
        return op._cached
    except AttributeError:
        pass

    try:
        for o in _OverloadedOperators[op.__class__.__name__]:
            (success, errormsg) = o._signature.matchWithInstruction(op)
            if success:
                ins = o(op1=op.op1(), op2=op.op2(), op3=op.op3(), target=op.target(), location=op.location())
                matches += [ins]
    except KeyError:
        pass

    op._cached = matches
    return matches
