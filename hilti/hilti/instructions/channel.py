# $Id$
"""
Channels
~~~~~~~~

A channel is a high-performance data type for I/O operations that is designed
to efficiently transfer large volumes of data both between the host
application and HILTI and intra-HILTI components. 

The channel behavior depends on its type parameters which enable fine-tuning
along the following dimensions:
* Capacity. The capacity represents the maximum number of items a channel can
  hold. A full bounded channel cannot accomodate further items and a reader must
  first consume an item to render the channel writable again. By default,
  channels are unbounded and can grow arbitrarily large.  
* Blocking behavior. Channels operate either in *blocking* or *non-blocking*
  mode. In blocking mode, reading/writing of an empty/full channel suspends the
  caller and blocks until a channel item is inserted/removed. In non-blocking
  mode, read/write operations return immediately when the channel is empty/full
  and throw an exception describing the error. The default mode of operation is
  non-blocking for both writes and reads.
"""

import llvm.core

import hilti.util as util

from hilti.constraints import *
from hilti.instructions.operators import *

@hlt.type("channel", 8)
class Channel(type.Container, type.Parameterizable):
    """Type for ``channel``. 

    t:  ~~ValueType - Type of the channel items. 
    
    cap: integer - The channel capacity, i.e., the maximum number of items per
    channel. If the capacity equals to 0, it is assumed that the channel is
    unbounded.
    """
    def __init__(self, t, cap, location=None):
        super(Channel, self).__init__(t, location)
        self._capacity = cap

    def capacity(self):
        """Returns channel capacity, i.e., the maximum number of items that the
        channel can hold.
        
        Returns: ~~ValueType - The channel capacity. A capacity of 0 denotes an
        unbounded channel.
        """
        return self._capacity

    ### Overridden from Type.
    
    def validate(self, vld):
        type.Container.validate(self, vld)
        if self._capacity < 0:
            vld.error(self, "channel capacity cannot be negative")
    
    ### Overridden from HiltiType.
    
    def llvmType(self, cg):
        """A ``channel`` is mapped to a ``hlt_channel *``."""
        return cg.llvmTypeGenericPointer()

    def typeInfo(self, cg):
        typeinfo = cg.TypeInfo(self)
        typeinfo.c_prototype = "hlt::channel *"
        typeinfo.to_string = "hlt::channel_to_string";
        return typeinfo

    ### Overridden from Parameterizable.
    
    def args(self):
        return type.Container.args(self) + [self._capacity]
    
@hlt.overload(New, op1=cType(cChannel), target=cReferenceOfOp(1))
class New(Operator):
    """Allocates a new instance of a channel with the same type as the target
    Reference.
    """
    def codegen(self, cg):
        top = operand.Type(self.op1().type())
        result = cg.llvmCallC("hlt::channel_new", [top])
        cg.llvmStoreInTarget(self, result)

@hlt.instruction("channel.write", op1=cReferenceOf(cChannel), op2=cItemTypeOfOp(1))
class Write(Instruction):
    """Writes an item into the channel referenced by *op1*. If the channel is
    full, the caller blocks.
    """
    def codegen(self, cg):
        op2 = self.op2().coerceTo(cg, self.op1().type().refType().itemType())
        cg.llvmCallC("hlt::channel_try_write", [self.op1(), op2])

@hlt.instruction("channel.read", op1=cReferenceOf(cChannel), target=cItemTypeOfOp(1))
class Read(Instruction):
    """Returns the next channel item from the channel referenced by *op1*. If
    the channel is empty, the caller blocks.
    """
    def codegen(self, cg):
        voidp = cg.llvmCallC("hlt::channel_try_read", [self.op1()])
        item_type = self.target().type()
        nodep = cg.builder().bitcast(voidp, llvm.core.Type.pointer(cg.llvmType(item_type)))
        cg.llvmStoreInTarget(self, cg.builder().load(nodep))

@hlt.instruction("channel.size", op1=cReferenceOf(cChannel), target=cIntegerOfWidth(64))
class Size(Instruction):
    """Returns the current number of items in the channel referenced by *op1*.
    """
    def codegen(self, cg):
        result = cg.llvmCallC("hlt::channel_get_size", [self.op1()])
        cg.llvmStoreInTarget(self, result)