.PHONY: lint fmt test

lint:
	uvx ruff check .

fmt:
	uvx ruff check --fix .

test:
	uv run pytest
