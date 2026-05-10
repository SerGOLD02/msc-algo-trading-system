import { Injectable } from '@angular/core';
import {
  interval, Observable, switchMap, startWith, shareReplay,
  retry, catchError, of
} from 'rxjs';
import { ApiService } from './api.service';
import { MarketSnapshot } from '../models/market.model';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class MarketService {
  constructor(private api: ApiService) {}

  snapshot$: Observable<MarketSnapshot> = interval(
    environment.priceRefreshMs
  ).pipe(
    startWith(0),
    switchMap(() => this.api.get<MarketSnapshot>('/market/snapshot').pipe(
      catchError(err => {
        console.warn('[MarketService] snapshot error:', err.message);
        return of(null as any);
      })
    )),
    retry({ count: 3, delay: 5000 }),
    shareReplay(1)
  );
}
