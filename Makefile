.PHONY: validate test hooks

validate:
	uv run python -m tools.validate

test:
	uv run pytest

hooks:
	@hookdir=$$(git rev-parse --git-path hooks); \
	mkdir -p "$$hookdir"; \
	ln -sf "$$(pwd)/tools/hooks/pre-commit" "$$hookdir/pre-commit"; \
	echo "installed pre-commit hook -> $$hookdir/pre-commit"
