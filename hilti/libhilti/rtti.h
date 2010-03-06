// $Id$
// 
// Run-time information about HILTI types.

#ifndef HILTI_RTTI_H
#define HILTI_RTTI_H

#include "exceptions.h"

   // HILTI_%doc-__HLT_TYPE-start
// Unique id values to identify a type. These numbers must match the type's
// _id class member in the Python module hilti.core.Type.
#define HLT_TYPE_ERROR     0 
#define HLT_TYPE_INTEGER   1 
#define HLT_TYPE_DOUBLE    2 
#define HLT_TYPE_BOOL      3 
#define HLT_TYPE_STRING    4 
#define HLT_TYPE_TUPLE     5
#define HLT_TYPE_REF       6
#define HLT_TYPE_STRUCT    7
#define HLT_TYPE_CHANNEL   8
#define HLT_TYPE_BYTES     9
#define HLT_TYPE_ENUM     10
#define HLT_TYPE_ENUM_LABEL 11
#define HLT_TYPE_ADDR     12
#define HLT_TYPE_PORT     13
#define HLT_TYPE_OVERLAY  14
#define HLT_TYPE_VECTOR   15
#define HLT_TYPE_LIST     16
#define HLT_TYPE_NET      17
#define HLT_TYPE_REGEXP   18
#define HLT_TYPE_BITSET   19
#define HLT_TYPE_EXCEPTION    20
#define HLT_TYPE_CONTINUATION 21
#define HLT_TYPE_CADDR 22
#define HLT_TYPE_LABEL 23
#define HLT_TYPE_ANY 24
#define HLT_TYPE_TIMER 25
#define HLT_TYPE_TIMER_MGR 26

#define HLT_TYPE_ITERATOR_BYTES  100
#define HLT_TYPE_ITERATOR_VECTOR 101
#define HLT_TYPE_ITERATOR_LIST   102
   // HILTI_%doc-__HLT_TYPE-end

   // %doc-hlt_type_info-start
typedef struct __hlt_type_info hlt_type_info;

struct __hlt_string;

struct __hlt_type_info {

    // The type's HLT_TYPE_* id.
    int16_t type; 
    
    // The type's size in bytes.
    int16_t size;

    // A readable version of the type's name. 
    const char* tag;

    // Number of type parameters.
    int16_t num_params;

    // Type-specific information; null if not used.
    void* aux;
    
    // List of type operations defined in libhilti functions. Pointers may be
    // zero to indicate that a type does not support an operation. 
    
    // Returns a readable representation of a value. 'type' is the type
    // information for the type being converted. 'obj' is a pointer to the
    // value stored with the C type as HILTI uses normally for values of that
    // type. 'options' is currently unused and will be always zero for now.
    // In the future, we might use 'options' to pass in hints about the
    // prefered format. 'expt' can be set to raise an exception.
    struct __hlt_string* (*to_string)(const hlt_type_info* type, const void* obj, int32_t options, hlt_exception** expt);
    int64_t (*to_int64)(const hlt_type_info* type, const void* obj, hlt_exception** expt);
    double (*to_double)(const hlt_type_info* type, const void* obj, hlt_exception** expt);

    // Calculates a hash of the value. If not given, the default is hash as
    // many bytes as size specifies. Note that the excpt argument will not be
    // used and will always be null.
    hlt_hash (*hash)(const hlt_type_info* type, const void* obj, hlt_exception** expt);
    
    // Compares to values for equality. If not given, the default is to
    // compare as many bytes as size specified.  Note that the excpt argument
    // will not be used and will always be null.
    int8_t (*equal)(const hlt_type_info* type1, const void* obj1, const hlt_type_info* type2, const void* obj2, hlt_exception** expt);
    
    // Type-parameters start here. The format is type-specific.
    char type_params[];
};
   // %doc-hlt_type_info-end

#endif