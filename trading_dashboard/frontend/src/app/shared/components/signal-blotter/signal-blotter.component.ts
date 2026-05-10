import {
  Component, Input, Output, EventEmitter, OnChanges, SimpleChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { WeeklySignalResponse, RatioSignal } from '../../../core/models/analytics.model';

@Component({
  selector: 'app-signal-blotter',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="blotter-wrapper">
      <div class="blotter-header">
        <div class="friday-selector">
          <label>{{ 'blotter.friday' | translate }}</label>
          <select (change)="onFridayChange($event)">
            <option *ngFor="let f of data?.available_fridays" [value]="f"
                    [selected]="f === data?.friday_date">
              {{ f }}
            </option>
          </select>
        </div>
        <div class="blotter-actions">
          <span class="stat active">{{ data?.n_active ?? 0 }} {{ 'blotter.active' | translate }}</span>
          <span class="stat filtered">{{ data?.n_filtered ?? 0 }} {{ 'blotter.filtered' | translate }}</span>
          <button class="csv-btn" (click)="downloadCsv()" [title]="'blotter.csv' | translate">⬇ CSV</button>
        </div>
      </div>

      <div class="blotter-regime" *ngIf="data"
           [class.crisis]="data.is_crisis">
        <span class="regime-dot"></span>
        {{ data.regime_name | translate }} ({{ data.regime_id }})
      </div>

      <div class="blotter-table-wrap" *ngIf="data && data.signals.length > 0; else noSignals">
        <table class="blotter-table">
          <thead>
            <tr>
              <th>{{ 'blotter.col_ratio' | translate }}</th>
              <th>{{ 'blotter.col_pair' | translate }}</th>
              <th>{{ 'blotter.col_direction' | translate }}</th>
              <th>{{ 'blotter.col_long' | translate }}</th>
              <th>{{ 'blotter.col_tfm' | translate }}</th>
              <th>{{ 'blotter.col_bq' | translate }}</th>
              <th>{{ 'blotter.col_status' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let s of data.signals"
                [class.active-row]="s.is_active"
                [class.filtered-row]="!s.is_active">
              <td class="ratio-id">{{ s.ratio_id }}</td>
              <td class="pair">{{ s.numerator }}/{{ s.denominator }}</td>
              <td>
                <span class="direction-badge" [class]="s.direction === 'LONG_NUM' ? 'long-num' : s.direction === 'LONG_DEN' ? 'long-den' : 'na'">
                  {{ (s.direction === 'LONG_NUM' ? '▲ ' + s.numerator : s.direction === 'LONG_DEN' ? '▼ ' + s.denominator : '—') }}
                </span>
              </td>
              <td class="long-tick">{{ s.long_ticker || '—' }}</td>
              <td>
                <span class="tfm-proj"
                      *ngIf="s.tfm_projection"
                      [class.tfm-bull]="s.tfm_projection === 'BULLISH'"
                      [class.tfm-bear]="s.tfm_projection === 'BEARISH'">
                  {{ s.tfm_projection === 'BULLISH' ? '▲' : '▼' }}
                </span>
                <span *ngIf="!s.tfm_projection" class="tfm-na">—</span>
              </td>
              <td>
                <div class="bq-cell">
                  <div class="bq-bar" [style.width.%]="s.bet_quality * 100"
                       [style.background]="getBqColor(s.bet_quality)"></div>
                  <span class="bq-val">{{ (s.bet_quality * 100).toFixed(1) }}%</span>
                </div>
              </td>
              <td>
                <span class="status-badge" [class]="s.status">
                  {{ getStatusLabel(s.status) | translate }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ng-template #noSignals>
        <div class="no-data">{{ 'blotter.no_signals' | translate }}</div>
      </ng-template>
    </div>
  `,
  styles: [`
    .blotter-wrapper { font-size: 13px; }
    .blotter-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 12px;
    }
    .friday-selector {
      display: flex; align-items: center; gap: 8px;
    }
    .friday-selector label {
      font-size: 12px; color: var(--color-text-muted); font-weight: 600;
    }
    .friday-selector select {
      padding: 5px 10px; border: 1px solid var(--color-border); border-radius: 6px;
      font-size: 12px; color: var(--color-text-primary); background: var(--color-surface);
      cursor: pointer; font-family: inherit;
    }
    .blotter-actions { display: flex; align-items: center; gap: 12px; }
    .stat {
      font-size: 12px; font-weight: 600; padding: 3px 10px;
      border-radius: 12px;
    }
    .stat.active { background: rgba(16,185,129,0.12); color: #10b981; }
    .stat.filtered { background: rgba(107,114,128,0.15); color: var(--color-text-muted); }

    .blotter-regime {
      display: flex; align-items: center; gap: 8px;
      font-size: 12px; color: var(--color-text-secondary); margin-bottom: 12px;
      padding: 6px 12px; border-radius: 8px;
      background: rgba(16,185,129,0.06);
    }
    .blotter-regime.crisis { background: rgba(239,68,68,0.06); color: #dc2626; }
    .regime-dot {
      width: 8px; height: 8px; border-radius: 50%; background: #10b981;
    }
    .blotter-regime.crisis .regime-dot { background: #ef4444; }

    .blotter-table-wrap { overflow-x: auto; max-height: 540px; overflow-y: auto; }
    .blotter-table-wrap::-webkit-scrollbar { width: 4px; height: 4px; }
    .blotter-table-wrap::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.3); border-radius: 4px; }

    .blotter-table {
      width: 100%; border-collapse: collapse; font-size: 12px;
    }
    .blotter-table th {
      padding: 8px 6px; text-align: left; font-size: 10px;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--color-text-muted); font-weight: 600; border-bottom: 2px solid var(--color-border);
      white-space: nowrap; position: sticky; top: 0; background: var(--color-surface); z-index: 1;
    }
    .blotter-table td {
      padding: 7px 6px; border-bottom: 1px solid var(--color-border-subtle);
      white-space: nowrap;
    }
    .active-row td { background: rgba(16,185,129,0.04); }
    .filtered-row td { opacity: 0.6; }
    tr:hover td { background: rgba(59,130,246,0.04) !important; }

    .ratio-id { font-weight: 700; color: var(--color-text-primary); }
    .pair { color: var(--color-text-secondary); }
    .long-tick { font-weight: 600; color: var(--color-text-primary); }

    .direction-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 11px; font-weight: 600;
    }
    .long-num { background: rgba(5,150,105,0.1); color: #059669; }
    .long-den { background: rgba(239,68,68,0.1); color: #dc2626; }
    .na { background: rgba(148,163,184,0.1); color: var(--color-text-muted); }

    .bq-cell { position: relative; width: 100px; height: 20px; }
    .bq-bar {
      position: absolute; left: 0; top: 2px;
      height: 16px; border-radius: 3px; transition: width 0.3s ease;
    }
    .bq-val {
      position: relative; z-index: 1; font-size: 11px;
      font-weight: 600; line-height: 20px; padding-left: 4px;
    }

    .status-badge { font-size: 11px; font-weight: 600; }
    .status-badge.attivo { color: #059669; }
    .status-badge.filtrato { color: var(--color-text-muted); }
    .status-badge.crisis { color: #ef4444; }
    .status-badge.no_data { color: var(--color-text-muted); }

    .tfm-proj {
      display: inline-block; font-size: 13px; font-weight: 700;
      width: 24px; text-align: center;
    }
    .tfm-bull { color: #059669; }
    .tfm-bear { color: #dc2626; }
    .tfm-na { color: var(--color-text-muted); font-size: 11px; }

    .csv-btn {
      padding: 4px 10px; border-radius: var(--radius-sm, 4px);
      border: 1px solid var(--color-border); background: var(--color-surface);
      color: var(--color-text-secondary); font-size: 12px;
      cursor: pointer; transition: all 0.15s ease;
      font-family: inherit;
    }
    .csv-btn:hover {
      background: var(--color-border); color: var(--color-text-primary);
    }

    .realized-cell {
      font-variant-numeric: tabular-nums;
      font-family: var(--font-numbers, monospace);
      font-size: 11px; font-weight: 600;
    }
    .realized-cell .positive { color: #10b981; }
    .realized-cell .negative { color: #ef4444; }
    .no-data-cell { color: var(--color-text-muted); }

    .no-data {
      text-align: center; padding: 40px; color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class SignalBlotterComponent implements OnChanges {
  @Input() data: WeeklySignalResponse | null = null;
  @Output() fridayChanged = new EventEmitter<string>();

  ngOnChanges(changes: SimpleChanges): void {}

  onFridayChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    this.fridayChanged.emit(target.value);
  }

  getBqColor(bq: number): string {
    if (bq >= 0.65) return 'rgba(5,150,105,0.35)';
    if (bq >= 0.55) return 'rgba(5,150,105,0.2)';
    if (bq >= 0.50) return 'rgba(245,158,11,0.2)';
    return 'rgba(148,163,184,0.15)';
  }

  getStatusLabel(status: string): string {
    switch(status) {
      case 'attivo': return 'blotter.status_active';
      case 'filtrato': return 'blotter.status_filtered';
      case 'crisis': return 'blotter.status_crisis';
      case 'no_data': return 'blotter.status_no_data';
      default: return status;
    }
  }

  downloadCsv(): void {
    if (!this.data?.friday_date) return;
    const url = `http://localhost:8000/api/signals/weekly/csv?friday=${this.data.friday_date}`;
    window.open(url, '_blank');
  }
}
