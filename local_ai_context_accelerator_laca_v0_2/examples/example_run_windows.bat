@echo off
py -m laca.cli scan examples\sample_project --focus "fix tests" --project-name "SampleProject" --out laca_out --top-k 10
