import {
  Component, Input, OnInit, OnDestroy, OnChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { interval, Subscription } from 'rxjs';
import { TranslatePipe } from '../../pipes/translate.pipe';

@Component({
  selector: 'app-countdown',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  template: `
    <div class="countdown" [class.imminent]="tick < 3600" [class.soon]="tick < 86400 && tick >= 3600">
      <span class="label">{{ 'header.next_close' | translate }}</span>
      <span class="timer">{{ display }}</span>
      <span class="sub">{{ 'header.signal_updates' | translate }}</span>
    </div>
  `,
  styles: [`
    .countdown {
      text-align: right; padding: 4px 0;
      .label { display: block; font-size: 11px; color: var(--color-text-muted); font-weight: 500; }
      .timer {
        display: block; font-size: 22px; font-weight: 700;
        color: #059669; letter-spacing: 1px;
        font-variant-numeric: tabular-nums;
        margin: 4px 0;
      }
      .sub { display: block; font-size: 10px; color: var(--color-text-muted); }
      &.soon .timer { color: #f59e0b; }
      &.imminent .timer {
        color: #ef4444;
        animation: pulse-text 1.5s infinite;
      }
    }

    @keyframes pulse-text {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.7; }
    }
  `]
})
export class CountdownComponent implements OnInit, OnDestroy, OnChanges {
  @Input() secondsRemaining = 0;

  display = '';
  tick = 0;
  private sub!: Subscription;

  ngOnInit(): void {
    this.tick = this.secondsRemaining;
    this.updateDisplay();
    this.sub = interval(1000).subscribe(() => {
      if (this.tick > 0) this.tick--;
      this.updateDisplay();
    });
  }

  ngOnChanges(): void {
    this.tick = this.secondsRemaining;
    this.updateDisplay();
  }

  private updateDisplay(): void {
    const d = Math.floor(this.tick / 86400);
    const h = Math.floor((this.tick % 86400) / 3600);
    const m = Math.floor((this.tick % 3600) / 60);
    const s = this.tick % 60;

    if (this.tick >= 86400) {
      this.display = `${d}g ${h}h`;
    } else if (this.tick >= 3600) {
      this.display = `${h}h ${String(m).padStart(2,'0')}m`;
    } else {
      this.display = `${m}m ${String(s).padStart(2,'0')}s`;
    }
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
