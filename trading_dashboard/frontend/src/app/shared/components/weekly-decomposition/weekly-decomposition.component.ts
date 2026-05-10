import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import {
  WeeklyDecompositionResponse, ContributionItem
} from '../../../core/models/analytics.model';

@Component({
  selector: 'app-weekly-decomposition',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="decomp-wrapper" *ngIf="data && data.contributions.length > 0; else noData">
      <div class="decomp-subtitle">
        {{ 'weekly_decomp.friday' | translate }} {{ data.friday_date }} → {{ data.next_friday }}
      </div>

      <div class="bar-row" *ngFor="let item of sortedContributions">
        <span class="bar-ticker">{{ item.ticker }}</span>
        <div class="bar-track">
          <div class="bar-fill"
               [class.positive]="item.contribution >= 0"
               [class.negative]="item.contribution < 0"
               [class.trigger-tp]="item.trigger_state === 'tp'"
               [class.trigger-sl]="item.trigger_state === 'sl'"
               [style.width.%]="getBarWidth(item)">
          </div>
        </div>
        <span class="bar-value"
              [class.positive]="item.contribution >= 0"
              [class.negative]="item.contribution < 0">
          {{ item.contribution >= 0 ? '+' : '' }}{{ (item.contribution * 100).toFixed(3) }}%
        </span>
      </div>

      <div class="total-row">
        <span class="bar-ticker total-label">{{ 'weekly_decomp.total' | translate }}</span>
        <span class="bar-value total-value"
              [class.positive]="data.total_return >= 0"
              [class.negative]="data.total_return < 0">
          {{ data.total_return >= 0 ? '+' : '' }}{{ (data.total_return * 100).toFixed(3) }}%
        </span>
      </div>
    </div>
    <ng-template #noData>
      <div class="no-data">{{ 'weekly_decomp.no_data' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .decomp-wrapper { font-size: 13px; }
    .decomp-subtitle {
      font-size: 11px; color: var(--color-text-muted);
      margin-bottom: 12px; font-variant-numeric: tabular-nums;
      font-family: var(--font-numbers, monospace);
    }

    .bar-row {
      display: flex; align-items: center; gap: 8px;
      padding: 4px 0;
    }
    .bar-ticker {
      width: 44px; font-size: 11px; font-weight: 700;
      color: var(--color-text-primary); text-align: right;
      flex-shrink: 0;
    }
    .bar-track {
      flex: 1; height: 14px; border-radius: 3px;
      background: var(--color-border-subtle);
      overflow: hidden;
    }
    .bar-fill {
      height: 100%; border-radius: 3px;
      transition: width 0.3s ease;
    }
    .bar-fill.positive { background: #10b981; }
    .bar-fill.negative { background: #ef4444; }
    /* Fix 3: Trigger state colors */
    .bar-fill.trigger-tp { background: #059669; border: 1px solid #ffffff; }
    .bar-fill.trigger-sl { background: #dc2626; opacity: 0.8; }

    .bar-value {
      width: 68px; text-align: right; font-size: 11px;
      font-weight: 600; flex-shrink: 0;
      font-variant-numeric: tabular-nums;
      font-family: var(--font-numbers, monospace);
    }
    .bar-value.positive { color: #10b981; }
    .bar-value.negative { color: #ef4444; }

    .total-row {
      display: flex; justify-content: space-between;
      align-items: center; margin-top: 10px;
      padding-top: 8px; border-top: 1px solid var(--color-border);
    }
    .total-label {
      font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--color-text-muted);
    }
    .total-value { font-size: 13px; }

    .no-data {
      text-align: center; padding: 30px;
      color: var(--color-text-muted); font-size: 14px;
    }
  `]
})
export class WeeklyDecompositionComponent {
  @Input() data: WeeklyDecompositionResponse | null = null;

  get sortedContributions(): ContributionItem[] {
    if (!this.data?.contributions) return [];
    return [...this.data.contributions].sort((a, b) => b.contribution - a.contribution);
  }

  getBarWidth(item: ContributionItem): number {
    if (!this.data?.contributions?.length) return 0;
    // Fix 5: Uniform normalization logic
    const maxAbs = Math.max(
      ...this.data.contributions.map(c => Math.abs(c.contribution)),
      0.0001
    );
    return (Math.abs(item.contribution) / maxAbs) * 100;
  }
}
