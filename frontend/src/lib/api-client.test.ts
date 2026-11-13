import { api, ApiError } from './api-client';

const vi = jest;

describe('Centralized Typed API Client', () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    // Clear cookies
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    });
  });

  it('attaches X-CSRF-Token header on POST requests when csrf_token cookie exists', async () => {
    document.cookie = 'csrf_token=test-csrf-token-12345; path=/';

    const fetchSpy = jest.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ id: '1', email: 'test@physioone.com', full_name: 'Test Staff' }),
    });
    global.fetch = fetchSpy;

    await api.login({ email: 'test@physioone.com', password: 'password123' });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(options.headers.get('X-CSRF-Token')).toBe('test-csrf-token-12345');
  });

  it('does not attach X-CSRF-Token on GET requests', async () => {
    document.cookie = 'csrf_token=test-csrf-token-12345; path=/';

    const fetchSpy = jest.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ is_initialized: true, owner_count: 1 }),
    });
    global.fetch = fetchSpy;

    await api.getSetupStatus();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, options] = fetchSpy.mock.calls[0];
    expect(options.headers.get('X-CSRF-Token')).toBeNull();
  });

  it('handles backend error responses and throws structured ApiError', async () => {
    const fetchSpy = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Invalid email or password.',
        },
      }),
    });
    global.fetch = fetchSpy;

    await expect(api.login({ email: 'wrong@test.com', password: 'bad' })).rejects.toThrow(
      'Invalid email or password.'
    );
  });

  it('handles detail string format from FastAPI HTTPException', async () => {
    const fetchSpy = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        detail: 'Cannot demote the last active Owner.',
      }),
    });
    global.fetch = fetchSpy;

    await expect(api.updateUser('user-id', { is_active: false })).rejects.toThrow(
      'Cannot demote the last active Owner.'
    );
  });
});
