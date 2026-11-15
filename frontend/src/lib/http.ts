/**
 * The single HTTP entry point for the whole application.
 *
 * Everything that makes this app's API contract awkward is handled here exactly once:
 *
 * 1. **Session cookie auth, not JWT.** Every request sends `credentials: 'include'`, so the
 *    `sessionid` cookie travels. There is no token, no `Authorization` header, and nothing is
 *    written to localStorage — a stolen XSS payload finds no credential to read.
 * 2. **CSRF on unsafe methods.** Django's `SessionAuthentication` requires
 *    `X-CSRFToken` to equal the `csrftoken` cookie on POST/PATCH/PUT/DELETE. The cookie is
 *    created by `GET /auth/csrf/` at boot (see `ensureCsrfCookie`) and is not readable by script
 *    until it exists, which is why the call must happen before the first write.
 * 3. **One error envelope.** The backend renders every failure as
 *    `{"error": {code, detail, fields?}}`. `ApiError` is the typed carrier of that shape, so no
 *    screen ever parses prose or branches on an HTTP status string.
 * 4. **403 means "not logged in".** The backend returns 403 (not 401) for anonymous access to a
 *    protected endpoint. `isUnauthenticated` is the one place that decision is made, and
 *    `ApiError` records which request produced it so the auth layer only redirects when
 *    `/auth/me/` is the thing that failed — a 403 from "you may not archive this project" must
 *    not log the user out.
 */

/** Value/label pair as returned by every choices endpoint. */
export interface Choice {
  value: string
  label: string
}

/** The paginated list envelope used by every list endpoint. */
export interface Paginated<T> {
  count: number
  total_pages: number
  page: number
  page_size: number
  next: string | null
  previous: string | null
  results: T[]
}

/** Shape of the `error` object inside the backend's error envelope. */
export interface ApiErrorPayload {
  code: string
  detail: string
  fields?: Record<string, string[]>
}

/** Query-string values accepted by `buildQuery`. `undefined`/`null`/`''` are dropped. */
export type QueryValue = string | number | boolean | null | undefined | Array<string | number>

/**
 * A failed API call, carrying the parsed envelope.
 *
 * `status` is kept separately from `code` because they answer different questions: `status` says
 * what HTTP said, `code` says what the *domain* said (`invalid_transition`, `permission_denied`,
 * `edit_window_closed`). Screens branch on `code` when they need precision and on `status`
 * otherwise.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string[]>
  readonly detail: string
  /** Request path that produced this error, e.g. `/auth/me/`. */
  readonly path: string

  constructor(init: {
    status: number
    code: string
    detail: string
    fields?: Record<string, string[]>
    path: string
  }) {
    super(init.detail)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.detail = init.detail
    this.fields = init.fields ?? {}
    this.path = init.path
  }

  /** Messages for one field, for mapping the envelope onto a form input. */
  fieldErrors(field: string): string[]
  /** Messages for any field whose key starts with `prefix` (e.g. `profile`). */
  fieldErrors(prefix: string, options: { prefix: true }): Record<string, string[]>
  fieldErrors(fieldOrPrefix: string, options?: { prefix: true }): string[] | Record<string, string[]> {
    if (options?.prefix) {
      const prefix = `${fieldOrPrefix}.`
      const collected: Record<string, string[]> = {}
      for (const [key, messages] of Object.entries(this.fields)) {
        if (key === fieldOrPrefix) {
          collected[key] = messages
        } else if (key.startsWith(prefix)) {
          collected[key.slice(prefix.length)] = messages
        }
      }
      return collected
    }
    return this.fields[fieldOrPrefix] ?? []
  }

  /** First message of the first offending field — a compact fallback for a toast. */
  firstFieldMessage(): string | null {
    for (const messages of Object.values(this.fields)) {
      if (messages.length > 0) return messages[0]
    }
    return null
  }
}

/** True when the envelope can only mean "there is no usable session". */
export function isUnauthenticated(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (error.status !== 401 && error.status !== 403) return false
  // A 403 on a permission check ("only managers may archive") is *not* a session problem.
  if (error.path !== '/auth/me/') return false
  return (
    error.status === 401 ||
    error.code === 'not_authenticated' ||
    error.code === 'authentication_failed' ||
    error.code === 'permission_denied' ||
    error.code === 'error'
  )
}

/** Turn any thrown value into a user-facing sentence. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail || 'The request failed.'
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

const API_BASE = '/api/v1'
const UNSAFE_METHODS = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

/** Read a cookie by name, or `null`. */
function readCookie(name: string): string | null {
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return null
}

/**
 * Build a query string, dropping empty values.
 *
 * Arrays are joined with commas because that is precisely the format the backend's
 * `CharInFilter` expects (`?status=NEW,IN_PROGRESS`). Booleans become `true`/`false`, which is
 * what `django_filters.BooleanFilter` parses.
 */
export function buildQuery(params: Record<string, QueryValue> | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, raw] of Object.entries(params)) {
    if (raw === undefined || raw === null || raw === '') continue
    if (Array.isArray(raw)) {
      const values = raw.filter((value) => value !== undefined && value !== null && value !== '')
      if (values.length === 0) continue
      search.set(key, values.map(String).join(','))
    } else {
      search.set(key, String(raw))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

/** Path relative to the API root, e.g. `/tickets/` or `https://…` for an absolute URL. */
export type ApiPath = string

function absoluteUrl(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  return `${API_BASE}${path}`
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** JSON body. Mutually exclusive with `formData`. */
  body?: unknown
  /** Multipart body (attachment upload). Mutually exclusive with `body`. */
  formData?: FormData
  signal?: AbortSignal
  /** Extra headers, merged over the defaults. */
  headers?: Record<string, string>
  /** Accept header; defaults to `application/json`. */
  accept?: string
}

/**
 * Perform one API request and return parsed JSON (or `undefined` for 204).
 *
 * This is the **only** function in the app that calls `fetch` against the API. Keeping that true
 * is what guarantees no screen forgets `credentials` or the CSRF header.
 */
export async function apiRequest<T>(path: ApiPath, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: options.accept ?? 'application/json' }
  if (options.headers) Object.assign(headers, options.headers)

  let body: BodyInit | undefined
  if (options.formData) {
    // Never set Content-Type for FormData: the browser must add the multipart boundary.
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  if (UNSAFE_METHODS.has(method)) {
    const token = readCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  let response: Response
  try {
    response = await fetch(absoluteUrl(path), {
      method,
      headers,
      body,
      // The session cookie is the credential; without this the request is anonymous.
      credentials: 'include',
      signal: options.signal,
    })
  } catch (cause) {
    // Network-level failure: no envelope exists, so manufacture a comparable error.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError({
      status: 0,
      code: 'network_error',
      detail: 'Could not reach the server. Check your connection and try again.',
      path,
    })
  }

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    // A non-JSON body on an error status means something upstream (proxy, HTML error page).
    if (response.ok) {
      throw new ApiError({
        status: response.status,
        code: 'unexpected_response',
        detail: 'The server returned a response in an unexpected format.',
        path,
      })
    }
    throw new ApiError({
      status: response.status,
      code: 'unexpected_response',
      detail: `The server returned an unexpected ${response.status} response.`,
      path,
    })
  }

  const parsed: unknown = await response.json()

  if (!response.ok) throw toApiError(parsed, response.status, path)
  return parsed as T
}

/** Narrow an unknown JSON body into the project's error envelope. */
function toApiError(payload: unknown, status: number, path: string): ApiError {
  const fallback: ApiErrorPayload = {
    code: 'error',
    detail: 'The request failed.',
  }
  if (typeof payload !== 'object' || payload === null || !('error' in payload)) {
    return new ApiError({ status, path, ...fallback })
  }
  const raw = (payload as { error: unknown }).error
  if (typeof raw !== 'object' || raw === null) {
    return new ApiError({ status, path, ...fallback })
  }
  const record = raw as Record<string, unknown>
  const code = typeof record.code === 'string' ? record.code : fallback.code
  const detail = typeof record.detail === 'string' ? record.detail : fallback.detail
  const fields = normalizeFields(record.fields)
  return new ApiError({ status, path, code, detail, fields })
}

function normalizeFields(raw: unknown): Record<string, string[]> {
  if (typeof raw !== 'object' || raw === null) return {}
  const fields: Record<string, string[]> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      fields[key] = value.map(String)
    } else if (typeof value === 'string') {
      fields[key] = [value]
    }
  }
  return fields
}

/** `GET` a JSON resource. */
export function apiGet<T>(path: ApiPath, params?: Record<string, QueryValue>, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(`${path}${buildQuery(params)}`, { method: 'GET', signal })
}

/** `POST` a JSON body. */
export function apiPost<T>(path: ApiPath, body?: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body })
}

/** `PATCH` a JSON body (partial update, the only update verb the API accepts). */
export function apiPatch<T>(path: ApiPath, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'PATCH', body })
}

/** `DELETE` a resource. Resolves to `undefined` on the API's 204 responses. */
export function apiDelete(path: ApiPath): Promise<void> {
  return apiRequest<void>(path, { method: 'DELETE' })
}

/** `POST` a multipart body under one file field. */
export function apiUpload<T>(path: ApiPath, file: File, field = 'file'): Promise<T> {
  const formData = new FormData()
  formData.append(field, file)
  return apiRequest<T>(path, { method: 'POST', formData })
}

/**
 * Fetch a private file as a blob.
 *
 * A plain `<a href="/api/v1/attachments/…/download/">` would be a *browser* navigation and would
 * not carry the session cookie's CSRF context the way `fetch` does; more importantly it cannot
 * report a failure, so the user would silently land on an error page. Fetching the bytes here and
 * handing them to an object URL keeps the download inside the authenticated XHR path.
 */
export async function apiDownload(path: ApiPath): Promise<Blob> {
  const headers: Record<string, string> = { Accept: 'application/octet-stream' }
  const response = await fetch(absoluteUrl(path), {
    method: 'GET',
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      const parsed: unknown = await response.json()
      throw toApiError(parsed, response.status, path)
    }
    throw new ApiError({
      status: response.status,
      code: 'download_failed',
      detail: 'The file could not be downloaded.',
      path,
    })
  }

  return response.blob()
}

/**
 * Save a blob to disk through a temporary object URL.
 *
 * The URL is revoked on the next frame: revoking synchronously can cancel the download in some
 * browsers, and never revoking leaks the blob for the tab's lifetime.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

/**
 * Prime the `csrftoken` cookie.
 *
 * Must run before the first unsafe request and before the user can submit anything. Called once by
 * `main.tsx` and awaited inside the login/register mutations as a safety net, so a stale tab that
 * lost its cookie recovers instead of failing with a 403 the user cannot interpret.
 */
let csrfPrimed: Promise<void> | null = null

export function ensureCsrfCookie(): Promise<void> {
  if (!csrfPrimed) {
    csrfPrimed = apiGet<unknown>('/auth/csrf/', undefined)
      .then(() => undefined)
      .catch(() => {
        // A failure here is not fatal: the request that needs the token will report its own error,
        // and the next call retries.
        csrfPrimed = null
      })
  }
  return csrfPrimed
}
