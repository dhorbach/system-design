PORT ?= 8000

.PHONY: run test

# Local preview without analytics (built into _dev, never deployed).
run:
	python3 scripts/build.py --dev
	python3 -m http.server $(PORT) --directory _dev

test:
	python3 -m unittest discover -s scripts -p 'test_*.py'
