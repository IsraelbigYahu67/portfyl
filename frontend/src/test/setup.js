import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver, but recharts' <ResponsiveContainer>
// requires it (used in a useEffect to size the chart). Stub it so components
// that render recharts charts don't crash during tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Every *ByRole query calls getComputedStyle (visibility checks). jsdom's
// first calls in a file are very slow -- it parses its built-in UA stylesheet
// and fills its selector/property-value caches per element type -- so the
// first role query cost ~330 ms on a 121-node DOM (vs ~15 ms warm). Under a
// full parallel run that cold query alone outran findBy*'s 1 s window and
// failed whichever test happened to be first in the file. Pay it here, in the
// untimed setup phase, against the tags our pages and recharts render.
{
  const warm = document.createElement("div");
  warm.innerHTML = '<main><header><nav><ul><li><a href="#">a</a></li></ul></nav></header>'
    + '<section><h1>h</h1><h2>h</h2><h3>h</h3><p><span>s</span><strong>b</strong><em>e</em><small>s</small></p>'
    + '<form><label>l<input></label><select><option>o</option></select><textarea></textarea><button>b</button></form>'
    + '<table><thead><tr><th>h</th></tr></thead><tbody><tr><td>c</td></tr></tbody></table>'
    + '<dl><dt>t</dt><dd>d</dd></dl><output>o</output><img alt="">'
    + '<svg><g><path></path><rect></rect><line></line><circle></circle><text>t</text></g></svg></section></main>';
  document.body.append(warm);
  for (const el of warm.getElementsByTagName("*")) getComputedStyle(el);
  warm.remove();
}
