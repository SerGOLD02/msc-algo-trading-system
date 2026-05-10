import {
  Component, Input, OnChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import {
  EtfPerformanceResponse, EtfPerformanceItem
} from '../../../core/models/analytics.model';

@Component({
  selector: 'app-etf-performance',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="etf-perf-wrapper" *ngIf="data && data.etfs.length > 0; else noData">
      <div class="table-scroll">
        <table class="etf-table">
          <colgroup>
            <col class="col-ticker">
            <col class="col-metric">
            <col class="col-metric">
            <col class="col-metric">
            <col class="col-trades">
          </colgroup>
          <thead>
            <tr>
              <th class="sortable" (click)="sortBy('ticker')">
                {{ 'etf_perf_table.col_ticker' | translate }} {{ getSortIcon('ticker') }}
              </th>
              <th class="sortable num" (click)="sortBy('algo_return')">
                {{ 'etf_perf_table.col_algo' | translate }} {{ getSortIcon('algo_return') }}
              </th>
              <th class="sortable num" (click)="sortBy('bh_return')">
                {{ 'etf_perf_table.col_bh' | translate }} {{ getSortIcon('bh_return') }}
              </th>
              <th class="sortable num" (click)="sortBy('alpha')">
                {{ 'etf_perf_table.col_alpha' | translate }} {{ getSortIcon('alpha') }}
              </th>
              <th class="sortable num" (click)="sortBy('n_trades')">
                {{ 'etf_perf_table.col_trades' | translate }} {{ getSortIcon('n_trades') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let e of sortedEtfs">
              <td class="ticker-cell">{{ e.ticker }}</td>
              <td class="num">{{ (e.algo_return * 100).toFixed(2) }}%</td>
              <td class="num">{{ (e.bh_return * 100).toFixed(2) }}%</td>
              <td class="num"
                  [class.positive]="e.alpha > 0"
                  [class.negative]="e.alpha < 0">
                {{ e.alpha >= 0 ? '+' : '' }}{{ (e.alpha * 100).toFixed(2) }}%
              </td>
              <td class="num">{{ e.n_trades }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="perf-note" *ngIf="data">
        {{ 'etf_perf.period' | translate }} {{ data.start_date }} → {{ data.end_date }}
      </div>
    </div>
    <ng-template #noData>
      <div class="no-data">{{ 'etf_perf.no_data' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .etf-perf-wrapper { font-size: 13px; }
    .table-scroll { overflow-x: auto; max-height: 460px; overflow-y: auto; }
    .table-scroll::-webkit-scrollbar { width: 4px; height: 4px; }
    .table-scroll::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.3); border-radius: 4px; }

    .etf-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
    .col-ticker { width: 16%; }
    .col-metric { width: 24%; }
    .col-trades { width: 12%; }

    .etf-table th {
      padding: 10px 8px; text-align: left; font-size: 10px;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--color-text-muted); font-weight: 600;
      border-bottom: 2px solid var(--color-border);
      white-space: nowrap; position: sticky; top: 0;
      background: var(--color-surface); z-index: 1;
    }
    .etf-table th.sortable { cursor: pointer; user-select: none; }
    .etf-table th.sortable:hover { color: var(--color-text-primary); }

    .etf-table td {
      padding: 9px 8px; border-bottom: 1px solid var(--color-border-subtle);
      white-space: nowrap;
    }
    .etf-table tr:hover td { background: rgba(59,130,246,0.04); }

    .ticker-cell { font-weight: 700; color: var(--color-text-primary); }

    /* Fix 3: Left-aligned numeric columns */
    .num {
      text-align: left !important; font-variant-numeric: tabular-nums;
      font-family: var(--font-numbers, monospace);
    }
    .positive { color: #10b981; font-weight: 600; }
    .negative { color: #ef4444; font-weight: 600; }

    .perf-note {
      font-size: 11px; color: var(--color-text-muted);
      margin-top: 12px; text-align: right;
    }

    .no-data {
      text-align: center; padding: 40px;
      color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class EtfPerformanceComponent implements OnChanges {
  @Input() data: EtfPerformanceResponse | null = null;

  sortedEtfs: EtfPerformanceItem[] = [];
  sortKey: 'ticker' | 'algo_return' | 'bh_return' | 'alpha' | 'n_trades' = 'alpha';
  sortDir: 'asc' | 'desc' = 'desc';

  ngOnChanges(): void {
    this.sortData();
  }

  sortBy(key: string): void {
    if (this.sortKey === key) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortKey = key as typeof this.sortKey;
      this.sortDir = 'desc';
    }
    this.sortData();
  }

  getSortIcon(key: string): string {
    if (this.sortKey !== key) return '';
    return this.sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  private sortData(): void {
    if (!this.data?.etfs) { this.sortedEtfs = []; return; }
    this.sortedEtfs = [...this.data.etfs].sort((a, b) => {
      const av = (a as any)[this.sortKey];
      const bv = (b as any)[this.sortKey];
      if (typeof av === 'string') {
        return this.sortDir === 'asc'
          ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return this.sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });
  }
}
