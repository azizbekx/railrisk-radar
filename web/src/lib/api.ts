// Thin API client. All endpoints live under /api (Vite proxies to FastAPI on :8000 in dev).

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) window.dispatchEvent(new Event('rr:unauthorized'))
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail ?? msg } catch { /* not json */ }
    throw new ApiError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json() as Promise<T>
}

export const get = <T,>(path: string) => fetch(`/api${path}`, { credentials: 'same-origin' }).then(r => handle<T>(r))

export const post = <T,>(path: string, body?: unknown) =>
  fetch(`/api${path}`, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }).then(r => handle<T>(r))

export type StreamEvent<S = any, R = any> =
  | { event: 'step'; data: S }
  | { event: 'result'; data: R }
  | { event: 'done'; data: null }
  | { event: 'error'; data: string }

/** POST and read an NDJSON stream (see api/common.py stream / stream_steps). Calls onEvent per line.
 *  Resolves when the stream ends. Pass an AbortSignal to cancel. */
export async function streamPost<S = any, R = any>(
  path: string, body: unknown, onEvent: (e: StreamEvent<S, R>) => void, signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api${path}`, {
    method: 'POST', credentials: 'same-origin', signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok || !res.body) await handle(res)
  const reader = res.body!.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim()
      buf = buf.slice(i + 1)
      if (line) onEvent(JSON.parse(line))
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf))
}
