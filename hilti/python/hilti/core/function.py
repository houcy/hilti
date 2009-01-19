# $Id$
#
# A function. 

import location
import scope

class Function(object):
    def __init__(self, name, type, location = location.Location(), parentfunc = None):
        self._name = name
        self._type = type
        self._bodies = []
        self._location = location
        self._scope = scope.Scope()
        self._parent = parentfunc
        if parentfunc:
            self._scope = parentfunc._scope

    def name(self):
        return self._name
        
    def type(self):
        return self._type

    def scope(self):
        return self._scope
    
    def addID(self, id):
        self._scope.insert(id)
        
    def addBlock(self, b, clear_next=True):
        if self._bodies:
            self._bodies[-1].setNext(b)
            
        self._bodies += [b] 
        if clear_next:
            b.setNext(None)
    
    def blocks(self):
        return self._bodies

    def clearBlocks(self):
        self._bodies = []

    def lookupBlock(self, name):
        for b in self._bodies:
            if b.name() == name:
                return b
        return None
        
    def parentFunc(self):
        return self._parent
        
    def location(self):
        return self._location

    def __str__(self):
        return "function %s %s" % (self._type, self._name)
    
    # Visitor support.
    def dispatch(self, visitor):
        visitor.visit_pre(self)
        self._scope.dispatch(visitor)
        for b in self._bodies:
            b.dispatch(visitor)
        visitor.visit_post(self)
        
    
    
