"""Prepare a validated payload locally; never connects to the database."""
import ast
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
fields = ('participant_id student_name college_name division gmail enrolled_arm completion_status '
          'grade age_years gender prior_experience device_type weekly_study_hours learning_minutes '
          'code_runs learning_help_requests post_help_requests copy_events tasks_solved '
          'pre_score_pct post_score_pct transfer_score_pct withdrawal_score_pct post_minus_pre_pp '
          'normalized_gain withdrawal_minus_post_pp total_minutes normalized_gain_sq withdrawal_drop_sq').split()
int_fields = set(fields[7:9] + fields[12:24] + ['total_minutes'])
float_fields = {'normalized_gain', 'withdrawal_minus_post_pp', 'normalized_gain_sq', 'withdrawal_drop_sq'}
rows = []
with (root / 'sim015_036.tsv').open(encoding='utf-8-sig', newline='') as handle:
    for values in csv.reader(handle, delimiter='\t'):
        assert len(values) == len(fields), (values[0], len(values))
        row = {}
        for name, value in zip(fields, values):
            value = value.strip()
            row[name] = None if value == '' else int(value) if name in int_fields else float(value) if name in float_fields else value
        rows.append(row)
assert [r['participant_id'] for r in rows] == [f'SIM-{n:03}' for n in range(15, 37)]

# Extract just our prior fixture constructors and CODE data, without executing
# Django imports or the old participant-specific import routine.
tree = ast.parse((root / 'import_sim004_evaluation.py').read_text(encoding='utf-8-sig'))
nodes = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in {'c', 'html'}:
        nodes.append(node)
    elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CODE' for t in node.targets):
        nodes.append(node)
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
        target = node.value.func
        if isinstance(target.value, ast.Name) and target.value.id == 'CODE' and target.attr == 'update':
            nodes.append(node)
constructors = {}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<fixture-data>', 'exec'), constructors)
code, c, html = constructors['CODE'], constructors['c'], constructors['html']
code.update({
    'pre_c_code_05': c(r'''    int n, prime = 1;
    scanf("%d", &n);
    if (n < 2) prime = 0;
    for (int divisor = 2; divisor <= n / divisor; divisor++) {
        if (n % divisor == 0) { prime = 0; break; }
    }
    if (prime) printf("%d is Prime\n", n);
    else printf("%d is Not Prime\n", n);'''),
    'pre_html_code_03': html('<ol>\n<li><b>Bangla</b></li>\n<li><b>English</b></li>\n<li><b>ICT</b></li>\n</ol>'),
    'with_c_code_03': c(r'''    int base, exponent;
    long long result = 1;
    scanf("%d %d", &base, &exponent);
    for (int i = 0; i < exponent; i++) result *= base;
    printf("Result = %lld\n", result);'''),
    'with_c_code_05': c(r'''    int n, original, reverse = 0;
    scanf("%d", &n);
    original = n;
    while (n > 0) {
        reverse = reverse * 10 + n % 10;
        n /= 10;
    }
    if (reverse == original) printf("Palindrome = YES\n");
    else printf("Palindrome = NO\n");'''),
})
assert len(code) == 32
payload = {'rows': rows, 'code': code, 'bank_hash': 'cb2ce8f4634078b0a6de87bd776f7eb4a105cb5d2ee410d1f2f6a54b0c5ebdba'}
validator = ast.parse((root / 'import_sim015_036_batch.py').read_text(encoding='utf-8-sig'))
validation_nodes = [n for n in validator.body if isinstance(n, (ast.Import, ast.ImportFrom)) and
                    (isinstance(n, ast.Import) or n.module == 'decimal')]
validation_nodes += [n for n in validator.body if isinstance(n, ast.FunctionDef) and n.name in {'targets_for', 'validate_source'}]
validation_namespace = {}
exec(compile(ast.Module(body=validation_nodes, type_ignores=[]), '<source-validation>', 'exec'), validation_namespace)
for row in rows:
    validation_namespace['validate_source'](row)
path = root / 'sim015_036_payload.json'
path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding='utf-8')
print(json.dumps({'rows': len(rows), 'forms': sum(len(validation_namespace['targets_for'](r)) for r in rows), 'code_pool': len(code)}))
