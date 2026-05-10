import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import {
  RegimeStatsResponse, RegimeStatItem
} from '../../../core/models/analytics.model';

@Component({
  selector: 'app-regime-stats',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="regime-stats-wrapper" *ngIf="data && data.regimes.length > 0; else noData">
      <div class="regime-cards">
        <div class="regime-card" *ngFor="let r of data.regimes"
             [style.border-top-color]="getRegimeColor(r.regime_id)">
          <div class="regime-header">
            <span class="regime-badge" [style.background]="getRegimeColor(r.regime_id)">
              {{ r.regime_id }}
            </span>
            <span class="regime-name">{{ r.regime_name | translate }}</span>
          </div>
          <div class="regime-metric">
            <span class="label">{{ 'regime_stats.win_rate' | translate }}</span>
            <div class="wr-bar-track">
              <div class="wr-bar-fill"
                   [style.width.%]="r.win_rate * 100"
                   [style.background]="getRegimeColor(r.regime_id)">
              </div>
            </div>
            <span class="value">{{ (r.win_rate * 100).toFixed(1) }}%</span>
          </div>
          <div class="regime-metric">
            <span class="label">{{ 'regime_stats.avg_return' | translate }}</span>
            <span class="value"
                  [class.positive]="r.avg_return >= 0"
                  [class.negative]="r.avg_return < 0">
              {{ r.avg_return >= 0 ? '+' : '' }}{{ (r.avg_return * 100).toFixed(2) }}%
            </span>
          </div>
          <div class="regime-metric">
            <span class="label">{{ 'regime_stats.n_trades' | translate }}</span>
            <span class="value">{{ r.total_trades }}</span>
          </div>
          <div class="regime-metric">
            <span class="label">{{ 'regime_stats.n_weeks' | translate }}</span>
            <span class="value">{{ r.n_weeks }}</span>
          </div>
        </div>
      </div>
    </div>
    <ng-template #noData>
      <div class="no-data">{{ 'regime_stats.no_data' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .regime-stats-wrapper { font-size: 13px; }
    .regime-cards {
      display: flex; gap: 10px; flex-wrap: wrap;
    }
    .regime-card {
      flex: 1 1 140px; min-width: 130px;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-top: 3px solid var(--color-border);
      border-radius: 8px; padding: 12px;
    }
    .regime-header {
      display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
    }
    .regime-badge {
      display: inline-flex; align-items: center; justify-content: center;
      width: 22px; height: 22px; border-radius: 50%;
      color: #fff; font-size: 11px; font-weight: 700;
    }
    .regime-name {
      font-size: 12px; font-weight: 600; color: var(--color-text-primary);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .regime-metric {
      display: flex; align-items: center; justify-content: space-between;
      gap: 6px; padding: 3px 0; font-size: 11px;
    }
    .regime-metric .label { color: var(--color-text-muted); }
    .regime-metric .value {
      font-weight: 700; color: var(--color-text-primary);
      font-variant-numeric: tabular-nums;
      font-family: var(--font-numbers, monospace);
    }
    .positive { color: #10b981 !important; }
    .negative { color: #ef4444 !important; }

    .wr-bar-track {
      flex: 1; height: 5px; border-radius: 3px;
      background: var(--color-border-subtle); margin: 0 4px;
    }
    .wr-bar-fill {
      height: 100%; border-radius: 3px;
      transition: width 0.3s ease;
    }

    .no-data {
      text-align: center; padding: 30px;
      color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class RegimeStatsComponent {
  @Input() data: RegimeStatsResponse | null = null;

  getRegimeColor(id: number): string {
    const colors: Record<number, string> = {
      0: '#10b981', // Growth — green
      1: '#14b8a6', // Moderate Growth — teal
      2: '#eab308', // Consolidation — yellow
      3: '#f97316', // Stress — orange
      4: '#ef4444', // Crisis — red
    };
    return colors[id] ?? '#6b7280';
  }
}
