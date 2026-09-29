// Runs the offline mobile engine exactly as a browser would (plain scripts in a
// fresh global scope). Input on stdin: {"cases":[{"data":{},"age":50,"sex":"male"}]}.
// Output: one result per case, or {"error": message} when the engine rejects it.
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const dir = path.join(__dirname, '..', 'frontend', 'mobile')
const context = vm.createContext({ self: {} })
for (const file of ['evidence.js', 'engine.js']) vm.runInContext(fs.readFileSync(path.join(dir, file), 'utf8'), context, { filename: file })
const engine = context.self.NCDAIEngine
const input = JSON.parse(fs.readFileSync(0, 'utf8'))
const results = input.cases.map(({ data, age, sex }) => {
  try { return JSON.parse(JSON.stringify(engine.assess(data, age, sex))) } catch (error) { return { error: String(error.message || error) } }
})
process.stdout.write(JSON.stringify(results))
