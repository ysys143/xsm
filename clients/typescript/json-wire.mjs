/** JSON grammar validation plus duplicate-member rejection, without recursion. */
export function parseWireJson(text) {
  const value = JSON.parse(text);
  const stack = [];
  for (let index = 0; index < text.length;) {
    const character = text[index];
    if (character === '"') {
      const start = index++;
      while (text[index] !== '"') index += text[index] === '\\' ? 2 : 1;
      index++;
      const current = stack.at(-1);
      if (current?.keys && current.key) {
        const key = JSON.parse(text.slice(start, index));
        if (current.keys.has(key)) throw new SyntaxError('duplicate JSON member');
        current.keys.add(key);
        current.key = false;
      }
      continue;
    }
    if (character === '{') stack.push({ keys: new Set(), key: true });
    else if (character === '[') stack.push({});
    else if (character === '}' || character === ']') stack.pop();
    else if (character === ',' && stack.at(-1)?.keys) stack.at(-1).key = true;
    index++;
  }
  return value;
}
