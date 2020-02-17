#!/bin/bash

set -x
nosetests --with-coverage --cover-erase --cover-html --cover-html-dir=coverage --cover-package=. tests/test_geo.py tests/test_pgd.py tests/test_variable.py || exit 1

if [ "$USER" == "trygveasp" ]; then
  rm -rf /lustre/storeA/users/trygveasp/coverage
  mv coverage /lustre/storeA/users/trygveasp/coverage
fi
