from collections import defaultdict

class SymbolTable:
    def __init__(self):
        """
        Initializes a new, empty symbol table.
        Class scope variables (static, field) are stored in global_scope.
        Subroutine scope variables (arg, var) are stored in subroutine_scopes.
        """
        self.global_scope = {}
        self.subroutine_scopes = defaultdict(dict)
        self.current_scope = self.global_scope

        self.counters = {
            "static": 0, "field": 0, "arg": 0, "var": 0,
            "if": 0, "while": 0
        }

    def start_subroutine(self, name):
        """
        Starts a new subroutine scope, resetting relevant counters.
        """
        self.subroutine_scopes[name] = {}
        # self.current_scope = self.subroutine_scopes[name]
        self.counters["arg"] = 0
        self.counters["var"] = 0
        self.counters["if"] = 0
        self.counters["while"] = 0

    def define(self, name, var_type, kind):
        """
        Defines a new identifier and assigns it a running index.
        """
        if kind in {"static", "field"}:
            self.global_scope[name] = (var_type, kind, self.counters[kind])  # FIXED
        elif kind in {"arg", "var"}:
            self.current_scope[name] = (var_type, kind, self.counters[kind])  # FIXED

        self.counters[kind] += 1

    def globalsCount(self, kind):
        """
        Counts the number of variables of the given kind in the class scope.
        """
        return len([v for (k, v) in self.global_scope.items() if v[1] == kind])

    def varCount(self, kind):
        """
        Counts the number of variables of the given kind in the current scope.
        """
        return len([v for (k, v) in self.current_scope.items() if v[1] == kind])

    def lookup(self, name):
        """
        Retrieves identifier details (type, kind, index) if found, else None.
        """
        return self.current_scope.get(name) or self.global_scope.get(name)

    def type_of(self, name):
        """ Retrieves the type of the specified identifier. """
        entry = self.lookup(name)
        return entry[0] if entry else "NONE"

    def kind_of(self, name):
        """ Retrieves the kind of the specified identifier. """
        entry = self.lookup(name)
        return entry[1] if entry else "NONE"

    def index_of(self, name):
        """ Retrieves the index of the specified identifier. """
        entry = self.lookup(name)
        return entry[2] if entry else "NONE"

    def set_scope(self, name):
        """
        Sets the current scope to the specified subroutine or global scope.
        """
        if name == "global":
            self.current_scope = self.global_scope
        else:
            # if name not in self.subroutine_scopes:  # FIX: Initialize if missing
            #     self.subroutine_scopes[name] = {}
            self.current_scope = self.subroutine_scopes[name]

