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
# From a clean checkout: starts Neo4j AND Postgres and waits for both to be
# healthy, generates the warehouse (small, seed 42), compiles the graph, loads
# the runtime policy store (ADR 0010), then runs three real `tn` calls (kg
# schema, a term-resolution kg query, a governed warehouse query) and prints
# their envelopes. Each call also writes one audit_log row to Postgres.
demo:
	@echo ">> uv sync"
	uv sync
	@echo ">> starting Neo4j + Postgres (docker compose up -d --wait)"
	@# On a clean checkout this brings up and waits for the compose-owned services.
	@# If a healthy true-north-neo4j is already serving bolt (e.g. another checkout
	@# started it), reuse it instead of failing on the fixed container_name — but
	@# always ensure Postgres is up too.
	@if docker compose up -d --wait 2>/dev/null; then \
		echo "   compose services healthy"; \
	elif docker exec true-north-neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-true-north-dev}" 'RETURN 1' >/dev/null 2>&1; then \
		echo "   reusing already-running true-north-neo4j; ensuring Postgres is up"; \
		docker compose up -d postgres --wait; \
	else \
		echo "   ERROR: could not start or reach Neo4j" >&2; exit 1; \
	fi
	@echo ">> generating warehouse (scale small, seed 42)"
	cd source && uv run python -m generator.generate --scale small --seed 42
	@echo ">> compiling knowledge graph"
	uv run python -m knowledge_graph.compile
	@echo ">> loading runtime policy store (users.yaml -> Postgres)"
	uv run python -m governance.pg
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
