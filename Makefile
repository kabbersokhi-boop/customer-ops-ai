.PHONY: up down seed test lint workflows secret-scan verify eval logs clean

up:
	docker compose up -d --build

seed:
	docker compose exec api python scripts/seed_demo.py

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	PYTHONPATH=. .venv/bin/pytest -q

lint:
	.venv/bin/ruff check .

workflows:
	.venv/bin/python scripts/validate_workflows.py

secret-scan:
	.venv/bin/python scripts/secret_scan.py --history

eval:
	.venv/bin/python scripts/run_demo_eval.py

verify: lint workflows secret-scan test

clean:
	docker compose down -v
	rm -f customer_ops.db test_customer_ops.db
