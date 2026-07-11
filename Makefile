.PHONY: validate test hooks demo

validate:
	uv run python -m tools.validate

test:
	uv run pytest

hooks:
	@hookdir=$$(git rev-parse --git-path hooks); \
	mkdir -p "$$hookdir"; \
	ln -sf "$$(pwd)/tools/hooks/pre-commit" "$$hookdir/pre-commit"; \
	echo "installed pre-commit hook -> $$hookdir/pre-commit"

# One-command bring-up of the real services + a smoke over the governed CLI.
# From a clean checkout: starts Neo4j and waits for it to be healthy, generates
# the warehouse (small, seed 42), compiles the graph, then runs three real `tn`
# calls (kg schema, a term-resolution kg query, a governed warehouse query) and
# prints their envelopes.
demo:
	@echo ">> uv sync"
	uv sync
	@echo ">> starting Neo4j (docker compose up -d --wait)"
	@# On a clean checkout this brings up and waits for the compose-owned Neo4j.
	@# If a healthy true-north-neo4j is already serving bolt (e.g. another checkout
	@# started it), reuse it instead of failing on the fixed container_name.
	@if docker compose up -d --wait 2>/dev/null; then \
		echo "   compose Neo4j healthy"; \
	elif docker exec true-north-neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-true-north-dev}" 'RETURN 1' >/dev/null 2>&1; then \
		echo "   reusing already-running true-north-neo4j"; \
	else \
		echo "   ERROR: could not start or reach Neo4j" >&2; exit 1; \
	fi
	@echo ">> generating warehouse (scale small, seed 42)"
	cd source && uv run python -m generator.generate --scale small --seed 42
	@echo ">> compiling knowledge graph"
	uv run python -m knowledge_graph.compile
	@echo ""
	@echo "==== SMOKE 1/3: tn kg schema (tokenless) ===="
	uv run tn kg schema
	@echo ""
	@echo "==== SMOKE 2/3: tn kg query — resolve 'retention' to its variants ===="
	uv run tn kg query --token tok-analyst-binh "MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' OR any(a IN c.aliases WHERE a =~ '(?i).*retention.*') OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric) RETURN c, v, m"
	@echo ""
	@echo "==== SMOKE 3/3: tn query — net_revenue by channel (executive) ===="
	uv run tn query --token tok-exec-mai --metric net_revenue --group-by channel
	@echo ""
	@echo ">> demo complete"
