import {
  Component, Input, Output, EventEmitter, OnChanges, SimpleChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { ChronosBandsResponse, ChronosBand } from '../../../core/models/analytics.model';

@Component({
  selector: 'app-chronos-bands',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="bands-wrapper" *ngIf="hasData; else noData">

      <div class="bands-header">
        <div class="bands-legend">
          <span class="legend-item"><span class="leg-bar band-bg"></span> {{ 'chronos_bands.legend_band' | translate }}</span>
          <span class="legend-item"><span class="leg-line median-line"></span> {{ 'chronos_bands.legend_median' | translate }}</span>
          <span class="legend-item"><span class="leg-dot current-dot"></span> {{ 'chronos_bands.legend_current' | translate }}</span>
          <span class="legend-item"><span class="leg-tri tfm-tri-bull"></span> TFM t+5 {{ 'chronos_bands.legend_bull' | translate }}</span>
          <span class="legend-item"><span class="leg-tri tfm-tri-bear"></span> TFM t+5 {{ 'chronos_bands.legend_bear' | translate }}</span>
        </div>
        <div class="friday-selector">
          <label>{{ 'chronos_bands.friday' | translate }}</label>
          <select (change)="onFridayChange($event)">
            <option *ngFor="let f of data?.available_fridays" [value]="f"
                    [selected]="f === data?.friday_date">
              {{ f }}
            </option>
          </select>
        </div>
      </div>

      <div class="bands-table-wrap">
        <table class="bands-table">
          <thead>
            <tr>
              <th>{{ 'chronos_bands.col_ratio' | translate }}</th>
              <th>{{ 'chronos_bands.col_pair' | translate }}</th>
              <th>{{ 'chronos_bands.col_dir' | translate }}</th>
              <th class="band-col">{{ 'chronos_bands.col_band' | translate }}</th>
              <th>{{ 'chronos_bands.col_curr' | translate }}</th>
              <th>{{ 'chronos_bands.col_med' | translate }}</th>
              <th>TFM t+5</th>
              <th>{{ 'chronos_bands.col_proj' | translate }}</th>
              <th>{{ 'chronos_bands.col_status' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let b of sortedBands"
                [class.active-row]="b.is_active"
                [class.filtered-row]="!b.is_active">
              <td class="ratio-id">{{ b.ratio_id }}</td>
              <td class="pair">{{ b.numerator }}/{{ b.denominator }}</td>
              <td>
                <span class="dir-badge" [class]="b.direction === 'LONG_NUM' ? 'dir-long' : 'dir-short'">
                  {{ b.direction === 'LONG_NUM' ? ('LONG ' + b.numerator) : ('LONG ' + b.denominator) }}
                </span>
              </td>
              <td class="band-col">
                <div class="band-visual">
                  <div class="band-range"
                       [style.left.%]="getBandLeft(b)"
                       [style.width.%]="getBandWidth(b)">
                  </div>
                  <div class="band-median"
                       [style.left.%]="getPosition(b, b.median)">
                  </div>
                  <div class="band-current"
                       [style.left.%]="getPosition(b, b.current_value)"
                       [class.above]="b.current_value > b.median"
                       [class.below]="b.current_value <= b.median">
                  </div>
                  <div class="band-tfm"
                       *ngIf="b.tfm_t5 !== null && b.tfm_t5 !== undefined"
                       [style.left.%]="getPosition(b, b.tfm_t5!)"
                       [class.tfm-bullish]="b.tfm_projection === 'BULLISH'"
                       [class.tfm-bearish]="b.tfm_projection === 'BEARISH'">
                  </div>
                </div>
              </td>
              <td class="mono-val" [class.above]="b.current_value > b.median"
                  [class.below]="b.current_value <= b.median">
                {{ b.current_value.toFixed(4) }}
              </td>
              <td class="mono-val median-val">{{ b.median.toFixed(4) }}</td>
              <td class="mono-val tfm-val"
                  [class.tfm-bull-val]="b.tfm_projection === 'BULLISH'"
                  [class.tfm-bear-val]="b.tfm_projection === 'BEARISH'">
                {{ b.tfm_t5 !== null && b.tfm_t5 !== undefined ? b.tfm_t5!.toFixed(4) : '—' }}
              </td>
              <td>
                <span class="proj-badge"
                      *ngIf="b.tfm_projection"
                      [class.proj-bull]="b.tfm_projection === 'BULLISH'"
                      [class.proj-bear]="b.tfm_projection === 'BEARISH'">
                  {{ (b.tfm_projection === 'BULLISH' ? 'chronos_bands.proj_bull' : 'chronos_bands.proj_bear') | translate }}
                </span>
                <span *ngIf="!b.tfm_projection" class="proj-na">—</span>
              </td>
              <td>
                <span class="status-pill" [class.active]="b.is_active">
                  {{ (b.is_active ? 'blotter.status_active' : 'blotter.status_filtered') | translate }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ng-template #noData>
      <div class="no-data">{{ 'chronos_bands.waiting' | translate }}</div>
    </ng-template>
  `,
  styles: [`
    .bands-wrapper { font-size: 12px; }

    .bands-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 14px; flex-wrap: wrap; gap: 10px;
    }
    .bands-legend {
      display: flex; gap: 20px;
      font-size: 11px; color: var(--color-text-muted);
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
      cursor: pointer; font-family: var(--font-mono, monospace);
    }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .leg-bar {
      width: 24px; height: 8px; border-radius: 3px;
    }
    .band-bg { background: rgba(8, 145, 178, 0.15); border: 1px solid rgba(8, 145, 178, 0.3); }
    .leg-line {
      width: 16px; height: 2px; background: var(--color-text-secondary);
      border-top: 2px dashed var(--color-text-secondary); height: 0;
    }
    .median-line { border-top: 2px dashed var(--color-text-secondary); }
    .leg-dot {
      width: 8px; height: 8px; border-radius: 50%;
    }
    .current-dot { background: #059669; }
    .leg-tri {
      width: 0; height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
    }
    .tfm-tri-bull { border-bottom: 8px solid #059669; }
    .tfm-tri-bear { border-top: 8px solid #dc2626; }

    .bands-table-wrap {
      overflow-x: auto; max-height: 640px; overflow-y: auto;
    }
    .bands-table-wrap::-webkit-scrollbar { width: 4px; }
    .bands-table-wrap::-webkit-scrollbar-thumb { background: rgba(161,161,170,0.3); border-radius: 4px; }

    .bands-table {
      width: 100%; border-collapse: collapse; font-size: 11px;
    }
    .bands-table th {
      padding: 7px 6px; text-align: left; font-size: 10px;
      text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--color-text-muted); font-weight: 600;
      border-bottom: 2px solid var(--color-border);
      white-space: nowrap; position: sticky; top: 0;
      background: var(--color-surface); z-index: 1;
    }
    .bands-table td {
      padding: 6px 6px; border-bottom: 1px solid var(--color-border-subtle);
      white-space: nowrap; vertical-align: middle;
    }
    .active-row td { background: rgba(16, 185, 129, 0.04); }
    .filtered-row td { opacity: 0.55; }
    tr:hover td { background: rgba(8, 145, 178, 0.04) !important; }

    .ratio-id { font-weight: 700; color: var(--color-text-primary); font-family: var(--font-mono, monospace); }
    .pair { color: var(--color-text-secondary); }

    .dir-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 10px; font-weight: 600; letter-spacing: 0.3px;
    }
    .dir-long { background: rgba(5, 150, 105, 0.1); color: #059669; }
    .dir-short { background: rgba(220, 38, 38, 0.08); color: #dc2626; }

    .band-col { min-width: 200px; }

    .band-visual {
      position: relative; height: 16px; width: 100%;
      background: var(--color-bg); border-radius: 4px;
      border: 1px solid var(--color-border);
    }
    .band-range {
      position: absolute; top: 2px; bottom: 2px;
      background: rgba(8, 145, 178, 0.12);
      border: 1px solid rgba(8, 145, 178, 0.25);
      border-radius: 3px;
    }
    .band-median {
      position: absolute; top: 1px; bottom: 1px; width: 2px;
      background: var(--color-text-secondary);
      transform: translateX(-1px);
    }
    .band-current {
      position: absolute; top: 2px; width: 8px; height: 10px;
      border-radius: 50%;
      transform: translateX(-4px);
    }
    .band-current.above { background: #059669; }
    .band-current.below { background: #dc2626; }

    .band-tfm {
      position: absolute; top: 1px;
      width: 0; height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-bottom: 8px solid var(--color-text-muted);
      transform: translateX(-5px);
      z-index: 2;
    }
    .band-tfm.tfm-bullish {
      border-bottom-color: #059669;
    }
    .band-tfm.tfm-bearish {
      border-bottom-color: #dc2626;
      border-bottom: none;
      border-top: 8px solid #dc2626;
      top: auto; bottom: 1px;
    }

    .mono-val {
      font-family: var(--font-mono, 'JetBrains Mono', monospace);
      font-variant-numeric: tabular-nums;
      font-size: 11px; color: var(--color-text-secondary);
    }
    .mono-val.above { color: #059669; font-weight: 600; }
    .mono-val.below { color: #dc2626; font-weight: 600; }
    .median-val { color: var(--color-text-muted); }
    .tfm-val { color: var(--color-text-muted); font-weight: 600; }
    .tfm-bull-val { color: #059669 !important; }
    .tfm-bear-val { color: #dc2626 !important; }

    .proj-badge {
      display: inline-block; padding: 2px 8px; border-radius: 4px;
      font-size: 10px; font-weight: 700; letter-spacing: 0.3px;
    }
    .proj-bull {
      background: rgba(5, 150, 105, 0.1); color: #059669;
    }
    .proj-bear {
      background: rgba(220, 38, 38, 0.08); color: #dc2626;
    }
    .proj-na { color: var(--color-text-muted); font-size: 11px; }

    .status-pill {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 10px; font-weight: 600;
      background: rgba(161, 161, 170, 0.12); color: var(--color-text-muted);
    }
    .status-pill.active {
      background: rgba(5, 150, 105, 0.1); color: #059669;
    }

    .no-data {
      text-align: center; padding: 48px; color: var(--color-text-muted); font-size: 13px;
    }
  `]
})
export class ChronosBandsComponent implements OnChanges {
  @Input() data: ChronosBandsResponse | null = null;
  @Output() fridayChanged = new EventEmitter<string>();

  hasData = false;
  sortedBands: ChronosBand[] = [];

  private globalMin = 0;
  private globalMax = 1;

  ngOnChanges(changes: SimpleChanges): void {
    if (this.data && this.data.bands.length > 0) {
      this.hasData = true;
      this.sortedBands = [...this.data.bands]
        .sort((a, b) => a.ratio_id.localeCompare(b.ratio_id));

      // Compute global scale for band visualization
      let allVals: number[] = [];
      for (const b of this.sortedBands) {
        allVals.push(b.lower_5, b.upper_95, b.current_value, b.median);
      }
      allVals = allVals.filter(v => !isNaN(v) && isFinite(v));
      if (allVals.length > 0) {
        this.globalMin = Math.min(...allVals);
        this.globalMax = Math.max(...allVals);
      }
    }
  }

  onFridayChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    this.fridayChanged.emit(target.value);
  }

  private toPercent(value: number, band: ChronosBand): number {
    const lo = band.lower_5;
    const hi = band.upper_95;
    const range = hi - lo;
    if (range === 0) return 50;
    // Use band range with 20% padding
    const padded_lo = lo - range * 0.2;
    const padded_hi = hi + range * 0.2;
    const padded_range = padded_hi - padded_lo;
    return Math.max(0, Math.min(100, ((value - padded_lo) / padded_range) * 100));
  }

  getBandLeft(b: ChronosBand): number {
    return this.toPercent(b.lower_5, b);
  }

  getBandWidth(b: ChronosBand): number {
    const left = this.toPercent(b.lower_5, b);
    const right = this.toPercent(b.upper_95, b);
    return Math.max(2, right - left);
  }

  getPosition(b: ChronosBand, value: number): number {
    return this.toPercent(value, b);
  }
}
