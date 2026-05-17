import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { YearlyBreakdownResponse } from '../../../core/models/analytics.model';
import { InfoTooltipComponent } from '../info-tooltip/info-tooltip.component';

@Component({
  selector: 'app-yearly-breakdown',
  standalone: true,
  imports: [CommonModule, InfoTooltipComponent, TranslatePipe],
  template: `
    <div class="yearly-card" *ngIf="data && data.years.length > 0">
      <h3>{{ 'yearly.title' | translate }}
        <app-info-tooltip [title]="'yearly.info_title' | translate"
          [text]="'yearly.info_text' | translate">
        </app-info-tooltip>
      </h3>
      <table class="yearly-table">
        <thead>
          <tr>
            <th>{{ 'yearly.col_year' | translate }}</th>
            <th class="col-algo">{{ 'yearly.col_cagr' | translate }}</th>
            <th class="col-algo">{{ 'yearly.col_sharpe' | translate }}</th>
            <th class="col-algo">{{ 'yearly.col_max_dd' | translate }}</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let y of data.years">
            <td class="year-cell">{{ y.year }}{{ y.year === currentYear ? ' (YTD)' : '' }}</td>
            <td class="col-algo" [class.winner]="y.cagr >= y.spy_cagr">
              {{ (y.cagr * 100).toFixed(1) }}%
            </td>
            <td class="col-algo" [class.winner]="y.sharpe >= y.spy_sharpe">
              {{ y.sharpe.toFixed(2) }}
            </td>
            <td class="col-algo" [class.winner]="y.max_drawdown >= y.spy_max_drawdown">
              {{ (y.max_drawdown * 100).toFixed(1) }}%
            </td>
          </tr>

        </tbody>
      </table>
      <div class="yearly-legend">
        <span class="leg-algo">{{ 'yearly.leg_algo' | translate }}</span>
        <span class="leg-note">{{ 'yearly.leg_note' | translate }}</span>
      </div>
    </div>
  `,
  styles: [`
    .yearly-card {
      font-size: 13px;
    }
    h3 {
      margin: 0 0 12px;
      font-size: 12px;
      font-weight: 600;
      color: var(--color-text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.7px;
    }
    .yearly-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .yearly-table th {
      padding: 6px 6px;
      font-weight: 600;
      text-align: right;
      color: var(--color-text-muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--color-border);
    }
    .yearly-table th:first-child { text-align: left; }
    .yearly-table td {
      padding: 7px 6px;
      text-align: right;
      font-family: var(--font-numbers, monospace);
      font-variant-numeric: tabular-nums;
      color: var(--color-text-secondary);
      border-bottom: 1px solid var(--color-border-subtle);
    }
    .yearly-table td:first-child {
      text-align: left;
      font-family: var(--font-sans);
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .yearly-table tr:last-child td { border-bottom: none; }
    .winner {
      color: #10b981 !important;
      font-weight: 700;
    }
    .year-cell { min-width: 70px; }
    .yearly-legend {
      margin-top: 10px;
      font-size: 10px;
      color: var(--color-text-muted);
      display: flex;
      gap: 12px;
    }
    .leg-algo { color: var(--color-text-secondary); }
    .leg-note { color: #10b981; }
  `]
})
export class YearlyBreakdownComponent {
  @Input() data: YearlyBreakdownResponse | null = null;
  currentYear = new Date().getFullYear();
}
