import { Component, Input, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';

@Component({
  selector: 'app-info-tooltip',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <span class="info-icon"
          (mouseenter)="onEnter()"
          (mouseleave)="onLeave()">i</span>
    <div class="info-popup" *ngIf="isOpen"
         [ngClass]="alignmentClass"
         (mouseenter)="onEnter()"
         (mouseleave)="onLeave()">
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
      left: 50%;
      transform: translateX(-50%);
      z-index: 1000;
      width: 320px;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: 10px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.3), 0 2px 8px rgba(0,0,0,0.2);
      animation: fadeIn 0.15s ease;
      max-width: calc(100vw - 32px);
      visibility: hidden; /* Prevent flickering during measurement */
    }
    
    .info-popup.measured {
      visibility: visible;
    }

    .info-popup.align-right {
      left: auto;
      right: 0;
      transform: translateX(0);
    }
    
    .info-popup.align-left {
      left: 0;
      transform: translateX(0);
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
    
    /* Support align classes and translate combined */
    .info-popup.align-left { transform: translateY(0) !important; }
    .info-popup.align-right { transform: translateY(0) !important; }
  `]
})
export class InfoTooltipComponent {
  @Input() text = '';
  @Input() title = 'Info';
  isOpen = false;
  alignmentClass = '';

  constructor(private el: ElementRef) {}

  onEnter() {
    this.isOpen = true;
    setTimeout(() => {
      const rect = this.el.nativeElement.getBoundingClientRect();
      const viewportWidth = document.documentElement.clientWidth;
      const popupWidth = 320; 
      
      const halfWidth = popupWidth / 2;
      const center = rect.left + rect.width / 2;
      
      if (center + halfWidth + 16 > viewportWidth) {
        this.alignmentClass = 'align-right measured';
      } else if (center - halfWidth - 16 < 0) {
        this.alignmentClass = 'align-left measured';
      } else {
        this.alignmentClass = 'measured';
      }
    });
  }

  onLeave() {
    this.isOpen = false;
    this.alignmentClass = '';
  }
}
