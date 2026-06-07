#!/usr/bin/env node
/**
 * JSONata expression evaluator.
 * Reads JSON { expression, payload } from stdin, writes result to stdout.
 */
const jsonata = require("jsonata");

async function main() {
  let raw = "";
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) raw += chunk;

  let input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    process.stderr.write("Invalid JSON input: " + e.message);
    process.exit(1);
  }

  const { expression, payload } = input;
  if (!expression || !payload) {
    process.stderr.write("Missing required fields: expression, payload");
    process.exit(1);
  }

  try {
    const expr   = jsonata(expression);
    const result = await expr.evaluate(payload);
    process.stdout.write(JSON.stringify(result ?? {}));
  } catch (e) {
    process.stderr.write("JSONata error: " + e.message);
    process.exit(2);
  }
}

main();
