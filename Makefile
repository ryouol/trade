.PHONY: proto build-cpp build-go build-py test test-py test-cpp lint clean help

help:
	@echo "Targets:"
	@echo "  proto       Regenerate protobuf types for C++/Go/Python/TS"
	@echo "  build-cpp   Build all C++ services into Docker images"
	@echo "  build-go    Build all Go services"
	@echo "  build-py    Sync Python workspace via uv"
	@echo "  test        Run every test suite"
	@echo "  test-py     Python tests (kalshi-auth, research/backtest)"
	@echo "  test-cpp    C++ tests via ctest"
	@echo "  lint        Lint everything"
	@echo "  clean       Remove build artifacts"

proto:
	@bash tools/codegen/codegen.sh

build-cpp:
	@cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
	@cmake --build build -j

build-go:
	@cd services/go/ws-gateway && go build ./...

build-py:
	@uv sync

test: test-py test-cpp

test-py:
	@uv run pytest services/python research

test-cpp:
	@if [ -d build ]; then cd build && ctest --output-on-failure; else echo "Run 'make build-cpp' first"; fi

lint:
	@uv run ruff check services/python research
	@uv run ruff format --check services/python research
	@cd services/go/ws-gateway && go vet ./...
	@pnpm -r lint

clean:
	@rm -rf build dist .turbo
	@find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@find . -name "*.pyc" -delete
