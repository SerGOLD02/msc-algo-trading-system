import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { OperationalStatus } from '../../../core/models/analytics.model';

@Component({
  selector: 'app-operational-status',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="op-status" *ngIf="data && data.last_friday">
      <span class="regime-pill" [class.crisis]="data.is_crisis"
            [class.growth]="data.regime_id === 0"
            [class.moderate]="data.regime_id === 1"
            [class.consolidation]="data.regime_id === 2"
            [class.stress]="data.regime_id === 3">
        {{ data.regime_name | translate }}
      </span>
      <span class="op-item">
        <span class="op-num">{{ data.n_active_trades }}</span> {{ 'op_status.trades' | translate }}
      </span>
      <span class="op-sep">·</span>
      <span class="op-item">
        {{ 'op_status.decay' | translate }} <span class="op-num">{{ data.decay_value.toFixed(3) }}</span>
      </span>
      <span class="op-sep">·</span>
      <span class="op-item op-date">
        {{ data.last_friday }}
      </span>
    </div>
  `,
  styles: [`
    .op-status {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      color: var(--color-text-secondary);
      font-family: var(--font-numbers, monospace);
      font-variant-numeric: tabular-nums;
      margin-top: 6px;
    }
    .regime-pill {
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .regime-pill.growth { background: rgba(16, 185, 129, 0.15); color: #10b981; }
    .regime-pill.moderate { background: rgba(34, 197, 94, 0.12); color: #22c55e; }
    .regime-pill.consolidation { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
    .regime-pill.stress { background: rgba(249, 115, 22, 0.12); color: #f97316; }
    .regime-pill.crisis { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
    .op-num { font-weight: 700; color: var(--color-text-primary); }
    .op-sep { color: var(--color-border); }
    .op-date { color: var(--color-text-muted); font-size: 11px; }
  `]
})
export class OperationalStatusComponent {
  @Input() data: OperationalStatus | null = null;
}
