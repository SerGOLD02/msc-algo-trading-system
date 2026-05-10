import { Observable, retry, catchError, of } from 'rxjs';
import { pipe } from 'rxjs';

/**
 * Shared pipe operator: retry with delay + catchError returning fallback.
 */
export function resilient<T>(fallback: T, retryCount = 2, delayMs = 3000) {
  return pipe(
    retry<T>({ count: retryCount, delay: delayMs }),
    catchError((err: any) => {
      console.warn('[API]', err.message);
      return of(fallback);
    })
  );
}
