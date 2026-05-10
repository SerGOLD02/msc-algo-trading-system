import { Component, inject, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LanguageService } from '../../../core/services/language.service';
import { TranslatePipe } from '../../pipes/translate.pipe';

interface EtfInfo {
  ticker: string;
  name: string;
  description: string;
  holdings: string;
}

@Component({
  selector: 'app-etf-glossary',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="glossary-grid">
      <div *ngFor="let etf of translatedEtfs()"
           class="etf-cell"
           (mouseenter)="hoveredTicker = etf.ticker"
           (mouseleave)="hoveredTicker = null">
        <span class="etf-ticker">{{ etf.ticker }}</span>
        <div class="etf-tooltip" *ngIf="hoveredTicker === etf.ticker">
          <div class="tooltip-title">{{ etf.ticker }} — {{ etf.name }}</div>
          <div class="tooltip-desc">{{ etf.description }}</div>
          <div class="tooltip-holdings">
            <span class="holdings-label">{{ 'glossary.holdings_label' | translate }}</span> {{ etf.holdings }}
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .glossary-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 4px;
    }
    .etf-cell {
      position: relative;
      text-align: center;
      padding: 6px 4px;
      border-radius: 4px;
      cursor: default;
      transition: background 0.15s;
    }
    .etf-cell:hover {
      background: var(--color-accent-light);
    }
    .etf-ticker {
      font-family: var(--font-numbers, monospace);
      font-size: 11px;
      font-weight: 700;
      color: var(--color-text-primary);
      letter-spacing: 0.3px;
    }
    .etf-tooltip {
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      transform: translateX(-50%);
      z-index: 1000;
      /* Fix 2: HD polish - dimensions and bounds */
      width: min(360px, calc(100vw - 32px));
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 12px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.35);
      padding: 14px 16px;
      text-align: left;
      animation: fadeUp 0.15s ease;
    }
    .tooltip-title {
      font-size: 14px;
      font-weight: 800;
      color: var(--color-text-primary);
      margin-bottom: 6px;
      letter-spacing: -0.2px;
    }
    .tooltip-desc {
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.6;
      margin-bottom: 10px;
    }
    .tooltip-holdings {
      font-size: 11px;
      color: var(--color-text-muted);
      line-height: 1.5;
    }
    .holdings-label {
      font-weight: 700;
      color: var(--color-text-secondary);
    }

    @keyframes fadeUp {
      from { opacity: 0; transform: translateX(-50%) translateY(4px); }
      to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
  `]
})
export class EtfGlossaryComponent {
  private langService = inject(LanguageService);
  hoveredTicker: string | null = null;
  
  translatedEtfs = signal<EtfInfo[]>([]);

  constructor() {
    effect(() => {
      this.langService.lang();
      this.updateTranslations();
    });
  }

  private updateTranslations() {
    const tickers = [
      'SPY', 'QQQ', 'IWM', 'MDY', 'DIA', 'EFA', 'EEM', 'XLB', 'XLE', 'XLF',
      'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'IYR', 'VNQ', 'SOXX', 'TLT',
      'IEF', 'SHY', 'LQD', 'GLD', 'SLV', 'UUP', 'SH', 'PSQ', 'RWM', 'VIXY', 'FXE'
    ];

    const list = tickers.map(t => ({
      ticker: t,
      name: this.langService.translate(`etf.${t}.name`),
      description: this.langService.translate(`etf.${t}.desc`),
      holdings: this.langService.translate(`etf.${t}.holdings`)
    }));
    
    this.translatedEtfs.set(list);
  }
}
