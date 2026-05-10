import {
  Component, Input, Output, EventEmitter, OnInit, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup } from '@angular/forms';
import { debounceTime, distinctUntilChanged } from 'rxjs';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';
import {
  BacktestParams, BacktestResponse
} from '../../../core/models/backtest.model';
import { InfoTooltipComponent } from '../info-tooltip/info-tooltip.component';

@Component({
  selector: 'app-param-sidebar',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, InfoTooltipComponent, TranslatePipe],
  template: `
    <div class="card param-card">
      <h3>{{ 'params.title' | translate }}
        <app-info-tooltip [title]="'params.tooltip_title' | translate"
          [text]="'params.tooltip_text' | translate">
        </app-info-tooltip>
      </h3>
      <p class="note">
        {{ 'params.note' | translate }}
      </p>

      <form [formGroup]="form">
        <div class="param-row" *ngFor="let p of paramDefs">
          <div class="param-label">
            <span>{{ p.label_key | translate }}</span>
            <span class="param-value">
              {{ form.get(p.key)?.value | number:'1.2-2' }}
            </span>
          </div>
          <input type="range"
                 [formControlName]="p.key"
                 [min]="p.min" [max]="p.max" [step]="p.step"
                 class="slider">
          <div class="param-hint">{{ p.hint_key | translate }}</div>
        </div>
      </form>

      <button class="reset-btn" (click)="resetParams()" type="button">
        {{ 'params.reset' | translate }}
      </button>

      <div class="custom-metrics" *ngIf="customBacktest">
        <h4>{{ 'params.metrics_title' | translate }}</h4>
        <div class="metric-row">
          <span>CAGR</span>
          <span class="metric-value">
            {{ (customBacktest.cagr * 100).toFixed(2) }}%
            <span class="delta" *ngIf="defaultBacktest"
                  [class.positive]="customBacktest.cagr >= defaultBacktest.cagr"
                  [class.negative]="customBacktest.cagr < defaultBacktest.cagr">
              {{ customBacktest.cagr >= defaultBacktest.cagr ? '↑' : '↓' }}
              {{ getCagrDelta() }}
            </span>
          </span>
        </div>
        <div class="metric-row">
          <span>{{ 'equity_chart.metric_sharpe' | translate }}</span>
          <span class="metric-value">
            {{ customBacktest.sharpe.toFixed(3) }}
            <span class="delta" *ngIf="defaultBacktest"
                  [class.positive]="customBacktest.sharpe >= defaultBacktest.sharpe"
                  [class.negative]="customBacktest.sharpe < defaultBacktest.sharpe">
              {{ customBacktest.sharpe >= defaultBacktest.sharpe ? '↑' : '↓' }}
              {{ getSharpeDelta() }}
            </span>
          </span>
        </div>
        <div class="metric-row">
          <span>{{ 'equity_chart.metric_max_dd' | translate }}</span>
          <span class="metric-value negative">
            {{ (customBacktest.max_drawdown * 100).toFixed(2) }}%
            <span class="delta" *ngIf="defaultBacktest"
                  [class.positive]="customBacktest.max_drawdown >= defaultBacktest.max_drawdown"
                  [class.negative]="customBacktest.max_drawdown < defaultBacktest.max_drawdown">
              {{ customBacktest.max_drawdown >= defaultBacktest.max_drawdown ? '↑' : '↓' }}
              {{ getMaxDdDelta() }}
            </span>
          </span>
        </div>
        <div class="metric-row">
          <span>{{ 'equity_chart.metric_calmar' | translate }}</span>
          <span class="metric-value">
            {{ customBacktest.calmar.toFixed(3) }}
            <span class="delta" *ngIf="defaultBacktest"
                  [class.positive]="customBacktest.calmar >= defaultBacktest.calmar"
                  [class.negative]="customBacktest.calmar < defaultBacktest.calmar">
              {{ customBacktest.calmar >= defaultBacktest.calmar ? '↑' : '↓' }}
              {{ getCalmarDelta() }}
            </span>
          </span>
        </div>
      </div>

      <div class="loading-hint" *ngIf="isLoading">
        {{ 'params.loading' | translate }}
      </div>
    </div>
  `,
  styles: [`
    .param-card {
      font-size: 13px;
      background: var(--color-surface);
      border-top: 2px solid #10b981;
      border-left: none;
      padding: 24px 28px;
    }
    .note { font-size: 12px; color: var(--color-text-muted); margin-bottom: 16px; line-height: 1.4; }
    /* Fix 2: Spacing polish */
    .param-row { margin-bottom: 24px; }
    .param-label {
      display: flex; justify-content: space-between;
      margin-bottom: 8px; color: var(--color-text-secondary);
    }
    .param-value { color: #10b981; font-weight: 700; font-family: var(--font-numbers, monospace); font-variant-numeric: tabular-nums; }
    .param-hint { font-size: 10.5px; color: var(--color-text-muted); margin-top: 6px; line-height: 1.3; }
    .slider {
      width: 100%; height: 6px; accent-color: #10b981;
      cursor: pointer; border-radius: 3px;
    }
    .custom-metrics {
      margin-top: 24px;
      border-top: 1px solid var(--color-border);
      padding-top: 20px;
    }
    .custom-metrics h4 {
      font-size: 11px; color: var(--color-text-muted);
      text-transform: uppercase; margin: 0 0 14px;
      letter-spacing: 0.8px; font-weight: 600;
    }
    .metric-row {
      display: flex; justify-content: space-between;
      padding: 7px 0; font-size: 13px; color: var(--color-text-secondary);
    }
    .metric-value { font-weight: 700; color: #f59e0b; font-family: var(--font-numbers, monospace); font-variant-numeric: tabular-nums; }
    .metric-value.negative { color: #ef4444; }
    .delta {
      font-size: 11px; margin-left: 6px; font-weight: 600;
    }
    .delta.positive { color: #10b981; }
    .delta.negative { color: #ef4444; }
    .loading-hint {
      text-align: center; color: #f59e0b;
      font-size: 12px; padding: 12px; animation: pulse 1.5s infinite;
    }
    .reset-btn {
      width: 100%; margin-top: 16px; padding: 10px 16px;
      background: var(--color-border-subtle); border: 1px solid var(--color-border);
      color: var(--color-text-secondary); font-size: 12px; font-weight: 600;
      border-radius: 8px; cursor: pointer;
      font-family: var(--font-sans, 'Inter', sans-serif);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      text-align: center; display: block;
    }
    .reset-btn:hover {
      background: var(--color-border); color: var(--color-text-primary); border-color: var(--color-border);
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
    }
  `]
})
export class ParamSidebarComponent implements OnInit {
  @Input() defaultParams!: BacktestParams;
  @Input() customBacktest: BacktestResponse | null = null;
  @Input() defaultBacktest: BacktestResponse | null = null;
  @Input() isLoading = false;
  @Output() paramsChanged = new EventEmitter<BacktestParams>();

  form!: FormGroup;

  paramDefs = [
    { key: 'bet_quality', label_key: 'params.bet_quality.label', min: 0.40,
      max: 0.65, step: 0.01,
      hint_key: 'params.bet_quality_hint' },
    { key: 'hrp_alpha', label_key: 'params.hrp_alpha.label', min: 0.0,
      max: 1.0, step: 0.05,
      hint_key: 'params.hrp_alpha_hint' },
    { key: 'k_sigmoid', label_key: 'params.k_sigmoid.label', min: 1.0,
      max: 20.0, step: 0.5,
      hint_key: 'params.k_sigmoid_hint' },
    { key: 'c_soglia', label_key: 'params.c_soglia.label', min: 0.30,
      max: 0.70, step: 0.05,
      hint_key: 'params.c_soglia_hint' },
    { key: 'k_up', label_key: 'params.k_up.label', min: 0.50,
      max: 3.00, step: 0.25,
      hint_key: 'params.k_up_hint' },
    { key: 'k_down', label_key: 'params.k_down.label', min: 0.50,
      max: 3.00, step: 0.25,
      hint_key: 'params.k_down_hint' },
  ];

  constructor(private fb: FormBuilder) {}

  ngOnInit(): void {
    this.form = this.fb.group({
      bet_quality: [this.defaultParams.bet_quality],
      hrp_alpha:   [this.defaultParams.hrp_alpha],
      k_sigmoid:   [this.defaultParams.k_sigmoid],
      c_soglia:    [this.defaultParams.c_soglia],
      k_up:        [this.defaultParams.k_up],
      k_down:      [this.defaultParams.k_down],
    });

    this.form.valueChanges.pipe(
      debounceTime(800),
      distinctUntilChanged(
        (a, b) => JSON.stringify(a) === JSON.stringify(b)
      )
    ).subscribe(vals => this.paramsChanged.emit(vals));
  }

  resetParams(): void {
    this.form.patchValue({
      bet_quality: this.defaultParams.bet_quality,
      hrp_alpha: this.defaultParams.hrp_alpha,
      k_sigmoid: this.defaultParams.k_sigmoid,
      c_soglia: this.defaultParams.c_soglia,
      k_up: this.defaultParams.k_up,
      k_down: this.defaultParams.k_down,
    });
  }

  getSharpeDelta(): string {
    if (!this.customBacktest || !this.defaultBacktest) return '';
    const delta = this.customBacktest.sharpe - this.defaultBacktest.sharpe;
    return (delta >= 0 ? '+' : '') + delta.toFixed(3);
  }

  getCagrDelta(): string {
    if (!this.customBacktest || !this.defaultBacktest) return '';
    const delta = (this.customBacktest.cagr - this.defaultBacktest.cagr) * 100;
    return (delta >= 0 ? '+' : '') + delta.toFixed(2) + '%';
  }

  getMaxDdDelta(): string {
    if (!this.customBacktest || !this.defaultBacktest) return '';
    const delta = (this.customBacktest.max_drawdown - this.defaultBacktest.max_drawdown) * 100;
    return (delta >= 0 ? '+' : '') + delta.toFixed(2) + '%';
  }

  getCalmarDelta(): string {
    if (!this.customBacktest || !this.defaultBacktest) return '';
    const delta = this.customBacktest.calmar - this.defaultBacktest.calmar;
    return (delta >= 0 ? '+' : '') + delta.toFixed(3);
  }
}
