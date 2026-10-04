// WP6 第 3 層：「買了才能用」用 Cedar（開源 cedar-wasm）寫，和 HephAgora 手寫版比較。
// 用法：npm i && node check.cjs
const cedar = require('@cedar-policy/cedar-wasm/nodejs');

// ---- 授權本體（與手寫版比較行數的部分）----
const schema = `
entity Skill;
entity User { purchased: Set<Skill> };
entity Tool { skill: Skill };
action callTool appliesTo { principal: User, resource: Tool };`;
const policies = { staticPolicies: `
permit(principal, action == Action::"callTool", resource is Tool)
when { principal.purchased.contains(resource.skill) };` };

// DB 資料 → Cedar entities（正式版要從購買紀錄、技能表查出來再轉）
const S = (id) => ({ __entity: { type: 'Skill', id } });
const toEntities = (purchases, tools) => [
  ...Object.entries(purchases).map(([u, skills]) => ({ uid: { type: 'User', id: u }, attrs: { purchased: skills.map(S) }, parents: [] })),
  ...Object.entries(tools).map(([t, skill]) => ({ uid: { type: 'Tool', id: t }, attrs: { skill: S(skill) }, parents: [] })),
  ...[...new Set(Object.values(tools))].map((s) => ({ uid: { type: 'Skill', id: s }, attrs: {}, parents: [] })),
];

cedar.preparsePolicySet('p', policies);
cedar.preparseSchema('s', schema);
function can(user, tool, entities) {
  const r = cedar.statefulIsAuthorized({
    principal: { type: 'User', id: user }, action: { type: 'Action', id: 'callTool' }, resource: { type: 'Tool', id: tool },
    context: {}, preparsedPolicySetId: 'p', preparsedSchemaName: 's', validateRequest: true, entities,
  });
  if (r.type === 'failure') throw new Error(JSON.stringify(r.errors));
  return r.response.decision === 'allow';
}
const listTools = (user, tools, entities) => Object.keys(tools).filter((t) => can(user, t, entities)); // tools/list 過濾
// ---- 授權本體結束 ----

const tools = { todo_add: 'todo', todo_list: 'todo', flight_search: 'flight' };
const entities = toEntities({ A: ['todo'], B: ['todo', 'flight'] }, tools);

console.log('cedar', cedar.getCedarVersion());
const v = cedar.validate({ schema, policies });
console.log('validate', v.type, JSON.stringify(v.validationErrors ?? v.errors));
const listA = listTools('A', tools, entities);
const listB = listTools('B', tools, entities);
console.log('tools/list A', listA);
console.log('tools/list B', listB);
console.log('A tools/call flight_search', can('A', 'flight_search', entities) ? 'allow' : 'deny');
if (listA.includes('flight_search') || !listB.includes('flight_search') || can('A', 'flight_search', entities)) throw new Error('授權結果不符預期');

const N = 10000;
const t0 = process.hrtime.bigint();
for (let i = 0; i < N; i++) can('B', 'flight_search', entities);
console.log('statefulIsAuthorized µs/次', (Number(process.hrtime.bigint() - t0) / N / 1000).toFixed(1));
console.log('OK');
