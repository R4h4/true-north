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

# One-command cold bring-up of BOTH tenants (retail + shinhan) + smokes over the
# governed CLI. From a clean checkout: starts Neo4j (retail 7687 + shinhan 7688)
# AND Postgres and waits for all healthy; then per tenant generates the warehouse
# (small, seed 42 — deterministic; parquet is gitignored so it is regenerated,
# CSVs are byte-identical to committed), compiles the graph into that tenant's
# Neo4j instance, and loads the runtime policy store into that tenant's Postgres
# schema (retail=public, shinhan=tn_shinhan; ADR 0010/0011). Each `tn` call writes
# one audit_log row to its tenant's schema.
demo:
	@echo ">> uv sync"
	uv sync
	@echo ">> starting Neo4j (retail + shinhan) + Postgres (docker compose up -d --wait)"
	@# On a clean checkout this brings up and waits for all compose-owned services.
	@# If a healthy true-north-neo4j is already serving bolt (e.g. another checkout
	@# started it), reuse it instead of failing on the fixed container_name — but
	@# always ensure the shinhan Neo4j and Postgres are up too.
	@if docker compose up -d --wait 2>/dev/null; then \
		echo "   compose services healthy"; \
	elif docker exec true-north-neo4j cypher-shell -u neo4j -p "$${NEO4J_PASSWORD:-true-north-dev}" 'RETURN 1' >/dev/null 2>&1; then \
		echo "   reusing already-running true-north-neo4j; ensuring shinhan Neo4j + Postgres are up"; \
		docker compose up -d neo4j-shinhan postgres --wait; \
	else \
		echo "   ERROR: could not start or reach Neo4j" >&2; exit 1; \
	fi
	@echo ">> [retail] generating warehouse (scale small, seed 42)"
	cd source && uv run python -m generator.generate --scale small --seed 42
	@echo ">> [retail] compiling knowledge graph"
	uv run python -m knowledge_graph.compile
	@echo ">> [retail] loading runtime policy store (users.yaml -> Postgres public)"
	uv run python -m governance.pg
	@echo ">> [shinhan] generating warehouse (scale small, seed 42)"
	cd source/datasets/shinhan && uv run python -m generator.generate --scale small --seed 42
	@echo ">> [shinhan] compiling knowledge graph (-> Neo4j 7688)"
	uv run python -m knowledge_graph.compile --dataset shinhan
	@echo ">> [shinhan] loading runtime policy store (users.yaml -> Postgres tn_shinhan)"
	uv run python -m governance.pg --dataset shinhan
	@echo ""
	@echo "==== RETAIL SMOKE 1/3: tn kg schema (tokenless) ===="
	uv run tn kg schema
	@echo ""
	@echo "==== RETAIL SMOKE 2/3: tn kg query — resolve 'retention' to its variants ===="
	uv run tn kg query --token tok-analyst-binh "MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' OR any(a IN c.aliases WHERE a =~ '(?i).*retention.*') OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric) RETURN c, v, m"
	@echo ""
	@echo "==== RETAIL SMOKE 3/3: tn query — net_revenue by channel (executive) ===="
	uv run tn query --token tok-exec-mai --metric net_revenue --group-by channel
	@echo ""
	@echo "==== SHINHAN SMOKE 1/2: tn --dataset shinhan whoami (executive) ===="
	uv run tn --dataset shinhan whoami --token tok-exec-sujin
	@echo ""
	@echo "==== SHINHAN SMOKE 2/2: tn --dataset shinhan query — npl_ratio by product (executive) ===="
	uv run tn --dataset shinhan query --token tok-exec-sujin --metric npl_ratio --group-by product
	@echo ""
	@echo ">> demo complete"
