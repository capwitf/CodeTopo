from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from base_parser import CallEdge, ParseResult, SymbolDef


@dataclass
class ResolvedCall:
    edge: CallEdge
    caller_def: SymbolDef | None
    callee_def: SymbolDef | None

    @property
    def is_cross_file(self) -> bool:
        return self.callee_def is not None and self.callee_def.file_path != self.edge.caller_file

    @property
    def is_resolved(self) -> bool:
        return self.callee_def is not None


@dataclass
class CallGraph:
    nodes: dict[str, SymbolDef] = field(default_factory=dict)
    edges: list[ResolvedCall] = field(default_factory=list)

    @property
    def cross_file_edges(self) -> list[ResolvedCall]:
        return [edge for edge in self.edges if edge.is_cross_file]

    @property
    def resolved_edges(self) -> list[ResolvedCall]:
        return [edge for edge in self.edges if edge.is_resolved]

    def stats(self) -> dict[str, object]:
        resolved_count = len(self.resolved_edges)
        edge_count = len(self.edges)
        return {
            "total_symbols": len(self.nodes),
            "total_calls": edge_count,
            "resolved_calls": resolved_count,
            "cross_file_calls": len(self.cross_file_edges),
            "resolution_rate": f"{(resolved_count / max(edge_count, 1) * 100):.1f}%",
        }


class SymbolIndex:
    def __init__(self) -> None:
        self._by_qualified: dict[str, list[SymbolDef]] = defaultdict(list)
        self._by_simple: dict[str, list[SymbolDef]] = defaultdict(list)
        self._all: list[SymbolDef] = []

    def add(self, symbol: SymbolDef) -> None:
        self._by_qualified[symbol.qualified_name].append(symbol)
        self._by_simple[symbol.name].append(symbol)
        self._all.append(symbol)

    def lookup_qualified(self, qualified_name: str) -> list[SymbolDef]:
        return self._by_qualified.get(qualified_name, [])

    def lookup_simple(self, name: str) -> list[SymbolDef]:
        return self._by_simple.get(name, [])

    def all_symbols(self) -> list[SymbolDef]:
        return self._all


class CallResolver:
    def __init__(self, parse_results: list[ParseResult], project_root: str = ".", verbose: bool = False):
        self.parse_results = parse_results
        self.project_root = project_root
        self.verbose = verbose
        self._index = SymbolIndex()

    def resolve(self) -> CallGraph:
        graph = CallGraph()

        for parse_result in self.parse_results:
            for symbol in parse_result.symbols:
                self._index.add(symbol)
                graph.nodes[f"{symbol.file_path}::{symbol.qualified_name}"] = symbol

        for parse_result in self.parse_results:
            local_scope = self._resolve_imports(parse_result)
            for edge in parse_result.call_sites:
                callee_def = self._resolve_callee(edge, local_scope)
                resolved_call = ResolvedCall(edge=edge, caller_def=None, callee_def=callee_def)
                graph.edges.append(resolved_call)

                if callee_def is not None:
                    edge.resolved_file = callee_def.file_path
                    edge.resolved_def = callee_def

        for resolved_call in graph.edges:
            caller_candidates = self._index.lookup_qualified(resolved_call.edge.caller_name)
            for candidate in caller_candidates:
                if candidate.file_path == resolved_call.edge.caller_file:
                    resolved_call.caller_def = candidate
                    break

        return graph

    def _resolve_imports(self, parse_result: ParseResult) -> dict[str, tuple[str, str]]:
        local_scope: dict[str, tuple[str, str]] = {}
        for decl in parse_result.imports:
            if not hasattr(decl, "module"):
                continue
            local_name = decl.alias or decl.name or decl.module.split(".")[-1]
            target_qualified = (
                f"{decl.module}.{decl.name}" if decl.name and decl.name != "*" else decl.module
            )
            local_scope[local_name] = (target_qualified, decl.module)
        return local_scope

    def _resolve_callee(
        self,
        edge: CallEdge,
        local_scope: dict[str, tuple[str, str]],
    ) -> SymbolDef | None:
        callee = edge.callee_name
        parts = callee.split(".")
        base = parts[0]

        if base in local_scope:
            target_qualified, module_name = local_scope[base]
            target_name = (
                f"{target_qualified}.{'.'.join(parts[1:])}" if len(parts) > 1 else target_qualified
            )

            candidates = self._index.lookup_qualified(target_name)
            if candidates:
                return candidates[0]

            fallback_base = parts[-1]
            candidates = self._index.lookup_simple(fallback_base)
            for candidate in candidates:
                if module_name.replace(".", "/") in candidate.file_path.replace("\\", "/"):
                    return candidate

        candidates = self._index.lookup_qualified(callee)
        if candidates:
            for candidate in candidates:
                if candidate.file_path == edge.caller_file:
                    return candidate
            return candidates[0]

        base_name = parts[-1]
        candidates = self._index.lookup_simple(base_name)
        if candidates:
            for candidate in candidates:
                if candidate.file_path == edge.caller_file:
                    return candidate
            return candidates[0]

        return None
