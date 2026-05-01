**Example 1: Basic Python Project Analysis**

Input:
```
analyze-codebase /path/to/python_project
```
Output/Result:
```
Language      Files   Lines   Code   Comments   Blanks
Python        15      2340    1800   240        300
Total         15      2340    1800   240        300
Estimated complexity hotspots:
  src/main.py (cyclomatic complexity: 15, lines: 320)
  src/utils.py (cyclomatic complexity: 12, lines: 180)
  src/parser.py (cyclomatic complexity: 10, lines: 145)
```

**Example 2: Polyglot Repository with Ignore Directories**

Input:
```
analyze-codebase /path/to/mixed_repo --ignore node_modules,test_fixtures
```
Output/Result:
```
Language      Files   Lines   Code   Comments   Blanks
Python        8       1200    900    150        150
JavaScript    22      3400    2600   300        500
YAML          4        250    200     20         30
Total         34      4850    3700   470        680
Estimated complexity hotspots:
  src/engine.py (cyclomatic complexity: 18, lines: 280)
  public/js/app.js (cyclomatic complexity: 14, lines: 210)
  src/api.js (cyclomatic complexity: 11, lines: 95)
Summary statistics:
  Total files: 34
  Total lines: 4850
  Most used language: JavaScript by lines
  Heaviest file: public/js/app.js (210 lines, complexity 14)
```

**Example 3: Quick Complexity-Only Report**

Input:
```
analyze-codebase /path/to/code --skip-counts --hotspots-only
```
Output/Result:
```
Estimated complexity hotspots:
  core/process.py (cyclomatic complexity: 25, lines: 400)
  lib/visualize.py (cyclomatic complexity: 20, lines: 310)
  cli/commands.py (cyclomatic complexity: 17, lines: 280)
Note: Only hotspots above threshold (complexity >= 10) are shown.
```[[ ## completed ## ]]