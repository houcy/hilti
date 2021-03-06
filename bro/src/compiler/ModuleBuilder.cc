#include <Traverse.h>
#include <Func.h>
#include "consts.bif.h"
#undef List

#include <list>

#include <util/util.h>

#include "Compiler.h"
#include "ModuleBuilder.h"
#include "ValueBuilder.h"
#include "ExpressionBuilder.h"
#include "StatementBuilder.h"
#include "TypeBuilder.h"
#include "ConversionBuilder.h"
#include "ASTDumper.h"
#include "../LocalReporter.h"
#include "../Converter.h"

// If we defined, we compile only a small subset of symbols:
//    - all event handlers with priority 42.
//    - all script functions with names starting with "foo".
//    - no global symbols defined outside of the global namespace.
//
// This is for testing as long as we can't compile everything yet.
#define LIMIT_COMPILED_SYMBOLS 0

namespace BifConst { namespace Hilti {  extern int save_hilti;  }  }

using namespace bro::hilti::compiler;

ModuleBuilder::ModuleBuilder(class Compiler* arg_compiler, shared_ptr<::hilti::CompilerContext> ctx, const std::string& namespace_)
	: BuilderBase(this), ::hilti::builder::ModuleBuilder(ctx, namespace_)
	{
	ns = namespace_;
	compiler = arg_compiler;
	expression_builder = new class ExpressionBuilder(this);
	statement_builder = new class StatementBuilder(this);
	type_builder = new class TypeBuilder(this);
	value_builder = new class ValueBuilder(this);
	conversion_builder = new class ConversionBuilder(this);

	importModule("Hilti");
	importModule("LibBro");
	}

ModuleBuilder::~ModuleBuilder()
	{
	delete expression_builder;
	delete statement_builder;
	delete type_builder;
	delete value_builder;
	}

shared_ptr<::hilti::Module> ModuleBuilder::Compile()
	{
#ifdef DEBUG
	if ( ns.size() )
		DBG_LOG_COMPILER("Beginning to compile namespace '%s'", ns.c_str());
	else
		DBG_LOG_COMPILER("Beginning to compile global namespace");
#endif

	try
		{
		for ( auto id : Compiler()->Globals(ns) )
			{
			auto type = id->Type();
			auto init = id->HasVal() && type->Tag() != TYPE_FUNC
				? HiltiValue(id->ID_Val(), type, true)
				: HiltiDefaultInitValue(type);

			addGlobal(HiltiSymbol(id), HiltiType(type), init);
			}

		for ( auto f : Compiler()->Functions(ns) )
			CompileFunction(f);
		}

	catch ( const BuilderException& e )
		{
		reporter::error(e.what());
		}

	DBG_LOG_COMPILER("Done compiling namespace %s", ns.c_str());

	if ( reporter::errors() > 0 )
		return nullptr;

	return Finalize();
	}

shared_ptr<::hilti::Module> ModuleBuilder::Finalize()
	{
	// We save the source here once so that we have it on disk for inspection
	// in case finalization/compilation fails. Normally the Manager will
	// later override it with the final version.
	//
	// TODO: We need to unify the save_* code. It should probably always
	// saved as quickly as possible.
	//
	if ( BifConst::Hilti::save_hilti )
		saveHiltiCode(::util::fmt("bro.%s.hlt", module()->id()->name()));

	FinalizeGlueCode();

	return module();
	}

class Compiler* ModuleBuilder::Compiler() const
	{
	return compiler;
	}

class ExpressionBuilder* ModuleBuilder::ExpressionBuilder() const
	{
	return expression_builder;
	}

class StatementBuilder* ModuleBuilder::StatementBuilder() const
	{
	return statement_builder;
	}

class TypeBuilder* ModuleBuilder::TypeBuilder() const
	{
	return type_builder;
	}

class ValueBuilder* ModuleBuilder::ValueBuilder() const
	{
	return value_builder;
	}

class ::bro::hilti::compiler::ConversionBuilder* ModuleBuilder::ConversionBuilder() const
	{
	return conversion_builder;
	}

string ModuleBuilder::Namespace() const
	{
	return ns;
	}

void ModuleBuilder::CompileFunction(const Func* func)
	{
#if LIMIT_COMPILED_SYMBOLS
	if ( string(func->Name()) != "bro_init" && string(func->Name()) != "to_lower" && strncmp(func->Name(), "foo", 3) != 0
             && strncmp(::extract_module_name(func->Name()).c_str(), "Log", 3) != 0 )
		return;
#endif

	auto id = ::global_scope()->Lookup(func->Name());
	assert(id);

	bool exported = id->IsExport();

	if ( func->GetKind() == Func::BUILTIN_FUNC )
		// We build wrappers in DeclareFunction().
		return;

	functions.push_back(func);

	auto bfunc = static_cast<const BroFunc*>(func);

	switch ( bfunc->FType()->Flavor() ) {
		case FUNC_FLAVOR_FUNCTION:
			CompileScriptFunction(bfunc, exported);
			break;

		case FUNC_FLAVOR_EVENT:
			CompileEvent(bfunc, exported);
			break;

		case FUNC_FLAVOR_HOOK:
			CompileHook(bfunc, exported);
			break;

		default:
			reporter::internal_error("unknown function flavor");
	}

	compiler->RegisterCompiledFunction(func);

	functions.pop_back();
	}

void ModuleBuilder::CreateFunctionStub(const BroFunc* func, create_stub_callback cb)
	{
	// We create stub function here that convers arguments and then
	// forward to the actual callee. The stub is externally visible and
	// provides the entry point for Bro's core using the Plugin's
	// Runtime*() methods. Stubs use HILTI-C calling convention.

	auto rtype = ::hilti::builder::type::byName("LibBro::BroVal");
	auto func_name = Compiler()->HiltiSymbol(func, module());
	auto stub_name = Compiler()->HiltiStubSymbol(func, module(), false);
	auto stub_result = ::hilti::builder::function::result(rtype);
	auto stub_args = ::hilti::builder::function::parameter_list();

	if ( lookupNode("bro-function-stub", stub_name) )
		return;

	DBG_LOG_COMPILER("Compiling stub for %s", func->Name());

	RecordType* args = func->FType()->Args();
	auto vtype = ::hilti::builder::type::byName("LibBro::BroVal");

	for ( int i = 0; i < args->NumFields(); i++ )
		{
		auto name = ::hilti::builder::id::node(::util::fmt("arg%d", i+1));
		auto arg = ::hilti::builder::function::parameter(name, vtype, false, nullptr);
		stub_args.push_back(arg);
		}

	exportID(stub_name);

	auto stub = pushFunction(stub_name, stub_result, stub_args, ::hilti::type::function::HILTI_C);

	::hilti::builder::tuple::element_list eight;
	::hilti::builder::tuple::element_list nine;

	eight.push_back(::hilti::builder::integer::create(8));
	nine.push_back(::hilti::builder::integer::create(9));

	auto profile_hilti_land_compiled_stubs = ::hilti::builder::tuple::create(eight);
	auto profile_hilti_land_compiled_code = ::hilti::builder::tuple::create(nine);

	Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
				  ::hilti::builder::id::create("LibBro::profile_start"),
				  profile_hilti_land_compiled_stubs);

	::hilti::builder::tuple::element_list call_args;

	for ( int i = 0; i < args->NumFields(); i++ )
		{
		auto arg = ::hilti::builder::id::create(::util::fmt("arg%d", i+1));
		auto btype = args->FieldType(i);
		auto harg = RuntimeValToHilti(arg, btype, false);
		call_args.push_back(harg);
		}

	Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
				  ::hilti::builder::id::create("LibBro::profile_stop"),
				  profile_hilti_land_compiled_stubs);

	Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
				  ::hilti::builder::id::create("LibBro::profile_start"),
				  profile_hilti_land_compiled_code);

	shared_ptr<::hilti::Expression> rval = addTmp("rval", vtype);
	cb(this, rval, ::hilti::builder::tuple::create(call_args));

	Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
				  ::hilti::builder::id::create("LibBro::profile_stop"),
				  profile_hilti_land_compiled_code);

	Builder()->addInstruction(::hilti::instruction::flow::ReturnResult, rval);
	popFunction();

	cacheNode("bro-function-stub", stub_name, stub);
	}

void ModuleBuilder::CompileScriptFunction(const BroFunc* func, bool exported)
	{
	if ( func->GetBodies().size() == 0 )
		return;

	DBG_LOG_COMPILER("Compiling script function %s", func->Name());

	auto func_name = Compiler()->HiltiSymbol(func, module());
	auto ftype = HiltiFunctionType(func->FType());

	assert(func->GetBodies().size() == 1);
	auto body = func->GetBodies()[0];

	auto id = ::hilti::builder::id::node(func_name);
	auto hfunc = pushFunction(id,
				  ast::checkedCast<::hilti::type::Function>(ftype),
				  nullptr);

	hfunc->addComment(func->Name());

	CompileFunctionBody(func, &body);

	popFunction();

	// We need to always export it due to how Bro puts most event
	// handlers into global space, and thus they may end up in a
	// different compilation unit but still call non-exported functions.
	//
	// if ( exported )
	exportID(id);

	CreateFunctionStub(func, [&](ModuleBuilder* mbuilder, shared_ptr<::hilti::Expression> rval, shared_ptr<::hilti::Expression> args)
			   {
			   auto ytype = func->FType()->YieldType();

			   if ( ytype->Tag() != ::TYPE_VOID )
				   {
				   shared_ptr<::hilti::Expression> result = mbuilder->addTmp("result", ftype->result()->type());

				   mbuilder->Builder()->addInstruction(result,
								       ::hilti::instruction::flow::CallResult,
								       ::hilti::builder::id::create(func_name),
								       args);

				   auto nval = RuntimeHiltiToVal(result, ytype);
				   Builder()->addInstruction(rval,
							     ::hilti::instruction::operator_::Assign,
							     nval);
				   }

			   else
				   {
				   mbuilder->Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
								       ::hilti::builder::id::create(func_name),
								       args);

				   Builder()->addInstruction(rval, ::hilti::instruction::flow::CallResult,
							     ::hilti::builder::id::create("LibBro::h2b_void"),
							     ::hilti::builder::tuple::create({}));
				   }
			   });
	}

void ModuleBuilder::CompileEventStub(const ::BroFunc* event)
	{
	auto event_name = Compiler()->HiltiSymbol(event, module());
	auto stub_name = Compiler()->HiltiStubSymbol(event, module(), false);

	// If there's no body, make sure the hook is declared.
	DeclareEvent(event);

	CreateFunctionStub(event, [&](ModuleBuilder* mbuilder, shared_ptr<::hilti::Expression> rval, shared_ptr<::hilti::Expression> args)
			   {
#if 0
			   Builder()->addInstruction(::hilti::instruction::hook::Run,
						     ::hilti::builder::id::create(event_name),
						     args);
#else
			   auto tc = ::hilti::builder::callable::type(::hilti::builder::void_::type());
			   auto rtc = ::hilti::builder::reference::type(tc);
			   auto c = addTmp("c", rtc);

			   Builder()->addInstruction(c,
						     ::hilti::instruction::callable::NewHook,
						     ::hilti::builder::type::create(tc),
						     ::hilti::builder::id::create(event_name),
						     args);

			   // TODO: This should queue the callable, not directl run it.
			   Builder()->addInstruction(::hilti::instruction::flow::CallCallableVoid, c);
#endif

			   // Clear return value, we don't have any.
			   Builder()->addInstruction(rval,
						     ::hilti::instruction::operator_::Assign,
						     ::hilti::builder::expression::default_(rval->type()));

			   });
	}

void ModuleBuilder::CompileEvent(const BroFunc* event, bool exported)
	{
	DBG_LOG_COMPILER("Compiling event function %s with %d bodies", event->Name(), event->GetBodies().size());

	auto event_name = Compiler()->HiltiSymbol(event, module());

	for ( auto b : event->GetBodies() )
		{
		// Compile the event body into a hook.

#if LIMIT_COMPILED_SYMBOLS
		if ( b.priority != 42 )
			// FIXME: Hack to select which handlers we want to compile.
			continue;
#endif

		auto type = HiltiFunctionType(event->FType());
		auto ftype = ast::checkedCast<::hilti::type::Hook>(type);

		if ( b.priority )
			ftype->attributes().add(::hilti::attribute::PRIORITY, b.priority);

		auto hook = pushHook(::hilti::builder::id::node(event_name), ftype, nullptr);

		hook->addComment(Location(event));

		CompileFunctionBody(event, &b);

		popHook();
		}

	CompileEventStub(event);
	}

void ModuleBuilder::CompileHook(const BroFunc* brohook, bool exported)
	{
	DBG_LOG_COMPILER("Compiling hook function %s", brohook->Name());

	auto hook_name = Compiler()->HiltiSymbol(brohook, module());
	auto stub_name = Compiler()->HiltiStubSymbol(brohook, module(), false);

	for ( auto b : brohook->GetBodies() )
		{
		auto type = HiltiFunctionType(brohook->FType());
		auto ftype = ast::checkedCast<::hilti::type::Hook>(type);

		if ( b.priority )
			ftype->attributes().add(::hilti::attribute::PRIORITY, b.priority);

		auto hook = pushHook(::hilti::builder::id::node(hook_name), ftype, nullptr);

		hook->addComment(Location(brohook));

		auto stop = newBuilder("stop_hook");
		auto return_ = newBuilder("return_from_hook");

		statement_builder->PushFlowState(StatementBuilder::FLOW_STATE_BREAK, stop->block());
		statement_builder->PushFlowState(StatementBuilder::FLOW_STATE_RETURN, return_->block());
		CompileFunctionBody(brohook, &b);
		statement_builder->PopFlowState();
		statement_builder->PopFlowState();

		Builder()->addInstruction(::hilti::instruction::flow::ReturnVoid);

		pushBuilder(return_);
		Builder()->addInstruction(::hilti::instruction::flow::ReturnVoid);
		popBuilder(return_);

		pushBuilder(stop);
		auto false_ = ::hilti::builder::boolean::create(false);
		Builder()->addInstruction(::hilti::instruction::hook::Stop, false_);
		popBuilder(stop);

		popHook();
		}

	// If there's no body, make sure the hook is declared.
	if ( brohook->GetBodies().empty() )
		DeclareHook(brohook);

	CreateFunctionStub(brohook, [&](ModuleBuilder* mbuilder, shared_ptr<::hilti::Expression> rval, shared_ptr<::hilti::Expression> args)
			   {
			   auto true_ = ::hilti::builder::boolean::create(true);
			   auto btype = ::hilti::builder::boolean::type();
			   shared_ptr<::hilti::Expression> result = mbuilder->addTmp("result", btype, true_);

			   Builder()->addInstruction(result, ::hilti::instruction::hook::Run,
						     ::hilti::builder::id::create(hook_name),
						     args);

			   auto nval = RuntimeHiltiToVal(result, ::base_type(::TYPE_BOOL));
			   Builder()->addInstruction(rval,
						     ::hilti::instruction::operator_::Assign,
						     nval);
			   });
	}

void ModuleBuilder::CompileFunctionBody(const ::Func* func, void* vbody)
	{
	// Note: we can't rely on the function's scope to understand which
	// local we have. For events, it seems that all locals from any
	// handler end up in the same scope. Furthermore, not all local are
	// represented in the scope; some may be introduced only through
	// InitStmts.

	std::string dbgmsg;

	if ( BifConst::Hilti::debug )
		{
		ODesc d;
		func->GetLocationInfo()->Describe(&d);
		std::string loc = d.Description();

		// Keep just the last two levels of the path.
		auto i = loc.rfind('/');
		if ( i > 0 && i != std::string::npos )
			i = loc.rfind('/', i - 1);

		if ( i != std::string::npos )
			loc = loc.substr(i + 1, std::string::npos);

		std::string fname = func->Name();

		if ( fname.rfind("::") == std::string::npos )
			fname = ::util::fmt("%s::%s", ::GLOBAL_MODULE_NAME, fname);

		dbgmsg = ::util::fmt("%s (%s)", fname, loc);
		Builder()->addDebugMsg("bro", ::util::fmt("> entering %s", dbgmsg));
		Builder()->debugPushIndent();
		}

	auto body = reinterpret_cast<::Func::Body*>(vbody);
	StatementBuilder()->Compile(body->stmts);

	if ( BifConst::Hilti::debug )
		{
		Builder()->debugPopIndent();
		Builder()->addDebugMsg("bro", ::util::fmt("< leaving %s", dbgmsg));
		}
	}

shared_ptr<::hilti::Expression> ModuleBuilder::DeclareFunction(const Func* func)
	{
	auto bfunc = static_cast<const BroFunc*>(func);

	switch ( bfunc->FType()->Flavor() ) {
		case FUNC_FLAVOR_FUNCTION:
			return DeclareScriptFunction(bfunc);

		case FUNC_FLAVOR_EVENT:
			return DeclareEvent(bfunc);

		case FUNC_FLAVOR_HOOK:
			return DeclareHook(bfunc);

		default:
			reporter::internal_error("unknown function flavor in DeclareFunction");
	}

	reporter::internal_error("cannot be reached");
	}

shared_ptr<::hilti::Expression> ModuleBuilder::DeclareScriptFunction(const ::BroFunc* func)
	{
	auto name = Compiler()->HiltiSymbol(func, module());

	// If the function is part of the same module, we'll compile it
	// separately.
	if ( ::extract_module_name(func->Name()) == module()->id()->name() )
		{
#if LIMIT_COMPILED_SYMBOLS
	if ( string(func->Name()) != "bro_init" && string(func->Name()) != "to_lower" )
#endif
		return ::hilti::builder::id::create(name);
		}

	auto id = ::hilti::builder::id::create(name);
	auto type = HiltiFunctionType(func->FType());

	declareFunction(::hilti::builder::id::node(name), ast::checkedCast<::hilti::type::Function>(type));
	return id;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::DeclareEvent(const ::BroFunc* event)
	{
	auto name = Compiler()->HiltiSymbol(event, module());
	auto type = HiltiFunctionType(event->FType());

	declareHook(::hilti::builder::id::node(name), ast::checkedCast<::hilti::type::Hook>(type));

	return ::hilti::builder::id::create(name);
	}

shared_ptr<::hilti::Expression> ModuleBuilder::DeclareHook(const ::BroFunc* hook)
	{
	auto name = Compiler()->HiltiSymbol(hook, module());
	auto type = HiltiFunctionType(hook->FType());

	declareHook(::hilti::builder::id::node(name), ast::checkedCast<::hilti::type::Hook>(type));

	return ::hilti::builder::id::create(name);
	}

std::shared_ptr<::hilti::Expression> ModuleBuilder::DeclareGlobal(const ::ID* id)
	{
	assert(id->IsGlobal() && ! id->AsType());

	auto symbol = HiltiSymbol(id);

	// std::cerr << id->Name() << " " << symbol << " " << id->ModuleName() << " " << module()->id()->name() << std::endl;

	// Only need to actually declare it if it's in a different module;
	// for the current module we'll generate the global variabel itself
	// elsewhere.
	if ( id->ModuleName() != module()->id()->name() )
		declareGlobal(symbol, HiltiType(id->Type()));

	return ::hilti::builder::id::create(symbol);
	}

std::shared_ptr<::hilti::Expression> ModuleBuilder::DeclareLocal(const ::ID* id)
	{
	assert(! id->IsGlobal() && ! id->AsType());

	auto symbol = HiltiSymbol(id);

	if ( ! hasLocal(symbol) )
		{
		auto type = id->Type();
		auto init = id->HasVal() && type->Tag() != TYPE_FUNC
				? HiltiValue(id->ID_Val(), id->Type(), true)
				: HiltiDefaultInitValue(type);

		addLocal(symbol, HiltiType(type), init);
		}

	return ::hilti::builder::id::create(symbol);
	}

const ::Func* ModuleBuilder::CurrentFunction() const
	{
	return functions.size() ? functions.back() : nullptr;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallFunction(const ::Expr* func, const ::FuncType* ftype, ListExpr* args, const ::BroType* target_type)
	{
	// If the expression references a callee by name, we call it directly
	// and purely inside HILTI. If not, we go through the Bro core.

	auto m = BroExprToFunc(func);

	bool success = m.first;
	auto bro_func = m.second;

	if ( ! success )
		// Cannot handle it ourselves, pass on to Bro.
		return HiltiCallFunctionViaBro(HiltiExpression(func), ftype, args, target_type);

	if ( ! bro_func )
		// Known, but no implementation.
		return nullptr;

	if ( bro_func->GetKind() == Func::BUILTIN_FUNC )
		{
		if ( Compiler()->HaveHiltiBif(bro_func->Name()) )
			{
			auto hargs = HiltiExpression(args, ftype->ArgTypes());
			return HiltiCallBuiltinFunctionHilti(static_cast<const BuiltinFunc*>(bro_func), hargs, target_type);
			}
		else
			return HiltiCallFunctionViaBro(HiltiExpression(func), ftype, args, target_type);
		}

	auto hargs = HiltiExpression(args, ftype->ArgTypes());

	switch ( ftype->Flavor() ) {
		case FUNC_FLAVOR_FUNCTION:
			return HiltiCallScriptFunctionHilti(bro_func, hargs, target_type);

		case FUNC_FLAVOR_EVENT:
			return HiltiCallEventHilti(bro_func, hargs, target_type);

		case FUNC_FLAVOR_HOOK:
			return HiltiCallHookHilti(bro_func, hargs, target_type);

		default:
			Error("unknown function flavor in CallFunction", func);
	}

	Error("cannot be reached in HiltiCallFunction", func);
	return nullptr;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallFunctionViaBro(shared_ptr<::hilti::Expression> func, const ::FuncType* ftype, ListExpr* args, const ::BroType* target_type)
	{
	switch ( ftype->Flavor() ) {
		case FUNC_FLAVOR_FUNCTION:
			return HiltiCallFunctionLegacy(func, ftype, args, target_type);

		case FUNC_FLAVOR_EVENT:
			return HiltiCallEventLegacy(func, ftype, args, target_type);

		case FUNC_FLAVOR_HOOK:
			return HiltiCallHookLegacy(func, ftype, args, target_type);

		default:
			reporter::internal_error("unknown function flavor in CallFunction");
	}

	reporter::internal_error("cannot be reached");
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallScriptFunctionHilti(const ::Func* func, shared_ptr<::hilti::Expression> args, const ::BroType* target_type)
	{
	auto ftype = func->FType();
	auto ytype = ftype->YieldType();
	assert(ytype);

	auto hfunc = DeclareFunction(func);

	if ( ytype->Tag() != TYPE_VOID )
		{
		auto result = Builder()->addTmp("result", HiltiType(ytype));
		Builder()->addInstruction(result, ::hilti::instruction::flow::CallResult, hfunc, args);
		return result;
		}

	else
		{
		Builder()->addInstruction(::hilti::instruction::flow::CallVoid, hfunc, args);
		return nullptr;
		}
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallEventHilti(const ::Func* func, shared_ptr<::hilti::Expression> args, const ::BroType* target_type)
	{
	auto hfunc = DeclareFunction(func);

	auto tc = ::hilti::builder::callable::type(::hilti::builder::void_::type());
	auto rtc = ::hilti::builder::reference::type(tc);
	auto c = addTmp("c", rtc);

	Builder()->addInstruction(c,
				  ::hilti::instruction::callable::NewHook,
				  ::hilti::builder::type::create(tc),
				  hfunc,
				  args);

	// TODO: This should queue the callable, not directl run it.
	Builder()->addInstruction(::hilti::instruction::flow::CallCallableVoid, c);

	return nullptr;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallHookHilti(const ::Func* func, shared_ptr<::hilti::Expression> args, const ::BroType* target_type)
	{
	auto true_ = ::hilti::builder::boolean::create(true);
	auto result = Builder()->addTmp("result", ::hilti::builder::boolean::type(), true_);
	auto hfunc = DeclareFunction(func);
	Builder()->addInstruction(result, ::hilti::instruction::hook::Run, hfunc, args);
	return result;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallBuiltinFunctionHilti(const ::Func* func, shared_ptr<::hilti::Expression> args, const ::BroType* target_type)
	{
	auto ftype = func->FType();

	const ::BroType* ytype = ftype->YieldType();

	if ( ytype->Tag() == TYPE_ANY && target_type->Tag() != TYPE_VOID )
		{
		assert(target_type);
		ytype = target_type;
		}

	assert(ytype);

	auto hftype = HiltiFunctionType(ftype);
	hftype->setCallingConvention(::hilti::type::function::HILTI_C);

	string bif_symbol;
	auto have = Compiler()->HaveHiltiBif(func->Name(), &bif_symbol);
	assert(have);

	declareFunction(bif_symbol, hftype);

	auto hfunc = ::hilti::builder::id::create(bif_symbol);

	if ( ytype->Tag() != TYPE_VOID )
		{
		auto result = Builder()->addTmp("bif_result", HiltiType(ytype));
		Builder()->addInstruction(result, ::hilti::instruction::flow::CallResult, hfunc, args);
		return result;
		}

	else
		{
		Builder()->addInstruction(::hilti::instruction::flow::CallVoid, hfunc, args);
		return nullptr;
		}
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallEventLegacy(shared_ptr<::hilti::Expression> fval, const ::FuncType* ftype, ListExpr* args, const ::BroType* target_type)
	{
	Error("CallEventLegacy not yet implemented");
	return 0;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallHookLegacy(shared_ptr<::hilti::Expression> fval, const ::FuncType* ftype, ListExpr* args, const ::BroType* target_type)
	{
	RecordType* fargs = ftype->Args();
	auto exprs = args->Exprs();

	::hilti::builder::tuple::element_list func_args;

	// This is apparently how a varargs function is defined in Bro ...
	//
	// TODO: Not tested for hooks ...
	bool var_args = (fargs->NumFields() == 1 && fargs->FieldType(0)->Tag() == TYPE_ANY);

	loop_over_list(exprs, i)
		{
		auto btype = var_args ? exprs[i]->Type() : fargs->FieldType(i);
		auto arg = HiltiExpression(exprs[i], btype);
		auto val = RuntimeHiltiToVal(arg, btype);
		func_args.push_back(val);
		}

	auto t = ::hilti::builder::tuple::create(func_args);
	auto ca = ::hilti::builder::tuple::create({ fval, t });

	auto vtype = ::hilti::builder::type::byName("LibBro::BroVal");
	auto rval = addTmp("rval", vtype);

	Builder()->addInstruction(rval, ::hilti::instruction::flow::CallResult,
				  ::hilti::builder::id::create("LibBro::call_legacy_result"), ca);

	auto result = RuntimeValToHilti(rval, ::base_type(TYPE_BOOL));
	BroUnref(rval);

	return result;
	}

shared_ptr<::hilti::Expression> ModuleBuilder::HiltiCallFunctionLegacy(shared_ptr<::hilti::Expression> fval, const ::FuncType* ftype, ListExpr* args, const ::BroType* target_type)
	{
	RecordType* fargs = ftype->Args();
	auto exprs = args->Exprs();

	::hilti::builder::tuple::element_list func_args;

	// This is apparently how a varargs function is defined in Bro ...
	bool var_args = (fargs->NumFields() == 1 && fargs->FieldType(0)->Tag() == TYPE_ANY);

	loop_over_list(exprs, i)
		{
		auto btype = var_args ? exprs[i]->Type() : fargs->FieldType(i);
		auto arg = HiltiExpression(exprs[i], btype);
		auto val = RuntimeHiltiToVal(arg, btype);
		func_args.push_back(val);
		}

	auto t = ::hilti::builder::tuple::create(func_args);
	auto ca = ::hilti::builder::tuple::create({ fval, t });

	const ::BroType* ytype = ftype->YieldType();

	if ( ytype->Tag() == TYPE_ANY )
		{
		assert(target_type);
		ytype = target_type;
		}

	shared_ptr<::hilti::Expression> result = nullptr;

	if ( ytype && ytype->Tag() != TYPE_VOID )
		{
		auto vtype = ::hilti::builder::type::byName("LibBro::BroVal");
		auto rval = addTmp("rval", vtype);

		Builder()->addInstruction(rval, ::hilti::instruction::flow::CallResult,
					  ::hilti::builder::id::create("LibBro::call_legacy_result"), ca);

		result = RuntimeValToHilti(rval, ytype);
		BroUnref(rval);
		}

	else
		{
		Builder()->addInstruction(::hilti::instruction::flow::CallVoid,
					  ::hilti::builder::id::create("LibBro::call_legacy_void"), ca);
		}

	return result;
	}


void ModuleBuilder::FinalizeGlueCode()
	{
	conversion_builder->FinalizeTypes();
	}

