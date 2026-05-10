import { Component, Input, Pipe, PipeTransform, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { MarketSnapshot, IndexSummary, AssetPrice } from '../../../core/models/market.model';

@Pipe({ name: 'sparkline', standalone: true })
export class SparklinePipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(item: IndexSummary | AssetPrice | null): SafeHtml {
    if (!item) return '';
    const pts = [
      -(item.change_1m_pct ?? 0),
      -(item.change_1w_pct ?? 0),
      0,
      item.change_1d_pct ?? 0
    ];
    const cumulative = [0, pts[0] + pts[1], pts[0] + pts[1] + pts[2], pts[0] + pts[1] + pts[2] + pts[3]];
    const min = Math.min(...cumulative);
    const max = Math.max(...cumulative);
    const range = max - min || 1;
    const w = 48, h = 18;
    const points = cumulative.map((v, i) => {
      const x = (i / 3) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const color = cumulative[3] >= cumulative[0] ? '#059669' : '#dc2626';
    const svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="vertical-align:middle"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }
}

@Component({
  selector: 'app-top-table',
  standalone: true,
  imports: [CommonModule, SparklinePipe, TranslatePipe],
  template: `
    <div class="tables-row">

      <div class="table-block">
        <h4>{{ 'market.indices' | translate }}</h4>
        <table>
          <thead>
            <tr>
              <th>{{ 'toptable.col_asset' | translate }}</th><th>{{ 'toptable.col_trend' | translate }}</th><th>{{ 'toptable.col_price' | translate }}</th>
              <th>{{ 'toptable.col_1d' | translate }}</th><th>{{ 'toptable.col_1w' | translate }}</th><th>{{ 'toptable.col_1m' | translate }}</th><th>{{ 'toptable.col_1y' | translate }}</th><th>{{ 'toptable.col_ytd' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let idx of snapshot?.indices">
              <td class="ticker">{{ idx.name | translate }}</td>
              <td class="sparkline-cell" [innerHTML]="idx | sparkline"></td>
              <td class="price">{{ idx.last_price | number:'1.2-2' }}</td>
              <td [class]="idx.change_1d_pct >= 0 ? 'pos' : 'neg'">
                {{ idx.change_1d_pct >= 0 ? '+' : '' }}{{ idx.change_1d_pct | number:'1.2-2' }}%
              </td>
              <td [class]="idx.change_1w_pct >= 0 ? 'pos' : 'neg'">
                {{ idx.change_1w_pct >= 0 ? '+' : '' }}{{ idx.change_1w_pct | number:'1.2-2' }}%
              </td>
              <td [class]="idx.change_1m_pct >= 0 ? 'pos' : 'neg'">
                {{ idx.change_1m_pct >= 0 ? '+' : '' }}{{ idx.change_1m_pct | number:'1.2-2' }}%
              </td>
              <td [class]="idx.change_1y_pct >= 0 ? 'pos' : 'neg'">
                {{ idx.change_1y_pct >= 0 ? '+' : '' }}{{ idx.change_1y_pct | number:'1.2-2' }}%
              </td>
              <td [class]="idx.change_ytd_pct >= 0 ? 'pos' : 'neg'">
                {{ idx.change_ytd_pct >= 0 ? '+' : '' }}{{ idx.change_ytd_pct | number:'1.2-2' }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="table-block scrollable">
        <h4>{{ 'market.universe' | translate }} ({{ snapshot?.assets?.length ?? 0 }})</h4>
        <table>
          <thead>
            <tr>
              <th>{{ 'toptable.col_ticker' | translate }}</th><th>{{ 'toptable.col_trend' | translate }}</th><th>{{ 'toptable.col_price' | translate }}</th>
              <th>{{ 'toptable.col_1d' | translate }}</th><th>{{ 'toptable.col_1w' | translate }}</th><th>{{ 'toptable.col_1m' | translate }}</th><th>{{ 'toptable.col_1y' | translate }}</th><th>{{ 'toptable.col_ytd' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let a of snapshot?.assets">
              <td class="ticker">{{ a.ticker }}</td>
              <td class="sparkline-cell" [innerHTML]="a | sparkline"></td>
              <td class="price" [class.flash-up]="flashMap[a.ticker] === 'up'" [class.flash-down]="flashMap[a.ticker] === 'down'">{{ a.last_price | number:'1.2-2' }}</td>
              <td [class]="a.change_1d_pct >= 0 ? 'pos' : 'neg'">
                {{ a.change_1d_pct >= 0 ? '+' : '' }}{{ a.change_1d_pct | number:'1.2-2' }}%
              </td>
              <td [class]="a.change_1w_pct >= 0 ? 'pos' : 'neg'">
                {{ a.change_1w_pct >= 0 ? '+' : '' }}{{ a.change_1w_pct | number:'1.2-2' }}%
              </td>
              <td [class]="a.change_1m_pct >= 0 ? 'pos' : 'neg'">
                {{ a.change_1m_pct >= 0 ? '+' : '' }}{{ a.change_1m_pct | number:'1.2-2' }}%
              </td>
              <td [class]="a.change_1y_pct >= 0 ? 'pos' : 'neg'">
                {{ a.change_1y_pct >= 0 ? '+' : '' }}{{ a.change_1y_pct | number:'1.2-2' }}%
              </td>
              <td [class]="a.change_ytd_pct >= 0 ? 'pos' : 'neg'">
                {{ a.change_ytd_pct >= 0 ? '+' : '' }}{{ a.change_ytd_pct | number:'1.2-2' }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>

    </div>
  `,
  styles: [`
    .tables-row {
      display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
    }
    .table-block h4 {
      font-size: 11px; color: var(--color-text-muted); margin: 0 0 12px;
      text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600;
    }
    .scrollable { max-height: 360px; overflow-y: auto; }
    .scrollable::-webkit-scrollbar { width: 4px; }
    .scrollable::-webkit-scrollbar-track { background: transparent; }
    .scrollable::-webkit-scrollbar-thumb { background: rgba(107,114,128,0.3); border-radius: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th {
      color: var(--color-text-muted); font-weight: 600; padding: 7px 6px;
      text-align: right; border-bottom: 2px solid var(--color-border);
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
      white-space: nowrap;
    }
    th:first-child { text-align: left; }
    td {
      padding: 6px 6px; text-align: right;
      border-bottom: 1px solid var(--color-border-subtle);
      font-family: var(--font-numbers, monospace);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    td:first-child { text-align: left; }
    .ticker { font-weight: 600; color: var(--color-text-primary); }
    .price { color: var(--color-text-secondary); }
    .pos { color: var(--color-accent); font-weight: 500; }
    .neg { color: var(--color-danger); font-weight: 500; }
    .sparkline-cell { text-align: center; padding: 4px 2px; }
    tr:hover td { background: var(--color-accent-light); }
    .flash-up {
      animation: flash-green 350ms ease-out;
    }
    .flash-down {
      animation: flash-red 350ms ease-out;
    }
    @keyframes flash-green {
      0% { background-color: rgba(16, 185, 129, 0.25); }
      100% { background-color: transparent; }
    }
    @keyframes flash-red {
      0% { background-color: rgba(239, 68, 68, 0.25); }
      100% { background-color: transparent; }
    }
  `]
})
export class TopTableComponent implements OnChanges {
  @Input() snapshot: MarketSnapshot | null = null;

  private previousPrices: Record<string, number> = {};
  flashMap: Record<string, 'up' | 'down' | ''> = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['snapshot'] && this.snapshot) {
      this.detectPriceChanges();
    }
  }

  private detectPriceChanges(): void {
    if (!this.snapshot?.assets) return;
    for (const asset of this.snapshot.assets) {
      const prev = this.previousPrices[asset.ticker];
      if (prev !== undefined && prev !== asset.last_price) {
        this.flashMap[asset.ticker] = asset.last_price > prev ? 'up' : 'down';
        setTimeout(() => { this.flashMap[asset.ticker] = ''; }, 350);
      }
      this.previousPrices[asset.ticker] = asset.last_price;
    }
  }
}
