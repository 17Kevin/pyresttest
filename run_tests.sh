#!/usr/bin/bash
# Core pieces
python -m unittest pyresttest.test_parsing pyresttest.test_binding pyresttest.test_generators pyresttest.test_contenthandling

# Integrated components
python -m unittest pyresttest.test_resttest pyresttest.test_tests pyresttest.test_benchmarks

