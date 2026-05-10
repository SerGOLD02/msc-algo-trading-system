import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';

@Component({
  selector: 'app-info-tooltip',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <span class="info-icon"
          (mouseenter)="isOpen = true"
          (mouseleave)="isOpen = false">i</span>
    <div class="info-popup" *ngIf="isOpen"
         (mouseenter)="isOpen = true"
         (mouseleave)="isOpen = false">
      <div class="info-popup-header">
        <span class="info-popup-title">{{ title | translate }}</span>
      </div>
      <div class="info-popup-body" [innerHTML]="text | translate"></div>
    </div>
  `,
  styles: [`
    :host {
      position: relative;
      display: inline-flex;
      align-items: center;
      margin-left: 8px;
    }

    .info-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px; height: 16px;
      font-size: 10px;
      font-weight: 600;
      font-style: italic;
      font-family: 'Georgia', serif;
      color: #0891b2;
      cursor: help;
      border-radius: 50%;
      border: 1.5px solid #0891b2;
      background: transparent;
      transition: all 0.2s ease;
      user-select: none;
      opacity: 0.7;
      line-height: 1;
    }
    .info-icon:hover {
      opacity: 1;
      background: rgba(8, 145, 178, 0.1);
      transform: scale(1.1);
    }

    .info-popup {
      position: absolute;
      top: calc(100% + 8px);
      left: -8px;
      z-index: 1000;
      width: 340px;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.3), 0 2px 8px rgba(0,0,0,0.2);
      animation: fadeIn 0.15s ease;
      /* Fix 2: HD polish - max bound check */
      max-width: 90vw;
    }

    .info-popup-header {
      padding: 10px 14px 8px;
      border-bottom: 1px solid var(--color-border-subtle);
    }
    .info-popup-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--color-text-primary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .info-popup-body {
      padding: 10px 14px 14px;
      font-size: 12.5px;
      line-height: 1.6;
      color: var(--color-text-secondary);
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `]
})
export class InfoTooltipComponent {
  @Input() text = '';
  @Input() title = 'Info';
  isOpen = false;
}
