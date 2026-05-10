import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslatePipe } from '../../pipes/translate.pipe';
import { ToastService } from '../../../core/services/toast.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="toast-container">
      @for (toast of toastService.toasts(); track toast.id) {
        <div class="toast" [class]="'toast-' + toast.type" (click)="toastService.dismiss(toast.id)">
          <span class="toast-icon">
            {{ toast.type === 'success' ? '✓' : toast.type === 'warning' ? '⚠' : toast.type === 'error' ? '✕' : 'ℹ' }}
          </span>
          <span class="toast-msg">{{ toast.message | translate }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .toast-container {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-width: 380px;
    }

    .toast {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 16px;
      border-radius: 8px;
      background: var(--color-surface);
      border: 1px solid var(--color-border);
      box-shadow: 0 4px 20px rgba(0,0,0,0.12);
      cursor: pointer;
      animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      font-size: 13px;
      color: var(--color-text-primary);
      transition: opacity 0.2s, transform 0.2s;
    }
    .toast:hover {
      transform: translateX(-4px);
    }

    .toast-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 22px; height: 22px;
      border-radius: 50%;
      font-size: 11px;
      font-weight: 700;
      flex-shrink: 0;
    }

    .toast-info .toast-icon { background: rgba(8, 145, 178, 0.12); color: #0891b2; }
    .toast-success .toast-icon { background: rgba(5, 150, 105, 0.12); color: #059669; }
    .toast-warning .toast-icon { background: rgba(217, 119, 6, 0.12); color: #d97706; }
    .toast-error .toast-icon { background: rgba(220, 38, 38, 0.12); color: #dc2626; }

    .toast-msg {
      flex: 1;
      line-height: 1.4;
    }

    @keyframes slideIn {
      from { opacity: 0; transform: translateX(30px); }
      to { opacity: 1; transform: translateX(0); }
    }
  `]
})
export class ToastContainerComponent {
  constructor(public toastService: ToastService) {}
}
