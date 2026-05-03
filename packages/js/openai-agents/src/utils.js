export function safeSerialize(obj) {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj === 'string' || typeof obj === 'number' || typeof obj === 'boolean') return obj;
  if (Array.isArray(obj)) return obj.map(safeSerialize);

  // Plain object or class instance
  const result = {};
  const source = typeof obj.toJSON === 'function'
    ? obj.toJSON()
    : (obj.export ? obj.export() : obj);

  for (const [key, value] of Object.entries(source ?? {})) {
    result[key] = safeSerialize(value);
  }
  return result;
}

export function cleanNulls(data) {
  if (data === null || data === undefined) return undefined;
  if (Array.isArray(data)) {
    const cleaned = data.map(cleanNulls).filter(v => v !== undefined);
    return cleaned.length ? cleaned : undefined;
  }
  if (typeof data === 'object') {
    const cleaned = {};
    for (const [k, v] of Object.entries(data)) {
      const c = cleanNulls(v);
      if (c !== undefined) cleaned[k] = c;
    }
    return Object.keys(cleaned).length ? cleaned : undefined;
  }
  return data;
}
