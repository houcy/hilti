
#ifndef HILTI_ID_H
#define HILTI_ID_H

#include "common.h"
#include "visitor-interface.h"

namespace hilti {

/// AST node for a source-level identifier.
class ID : public ast::ID<AstInfo>
{
public:
   /// Constructor.
   ///
   /// path: The name of the identifier, either scoped or unscoped.
   ///
   /// l: Associated location.
   ID(string path, const Location & l=Location::None) : ast::ID<AstInfo>(path, l) {}

   ACCEPT_VISITOR_ROOT();
private:
};

}

#endif