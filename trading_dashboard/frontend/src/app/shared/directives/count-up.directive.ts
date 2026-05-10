import {
  Directive, Input, ElementRef, OnChanges, SimpleChanges
} from '@angular/core';

@Directive({
  selector: '[appCountUp]',
  standalone: true,
})
export class CountUpDirective implements OnChanges {
  @Input('appCountUp') targetValue: number | string = 0;
  @Input() countDuration = 600; // ms
  @Input() countDecimals = 2;
  @Input() countPrefix = '';
  @Input() countSuffix = '';

  private currentValue = 0;
  private animationFrame: number | null = null;

  constructor(private el: ElementRef<HTMLElement>) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['targetValue']) {
      const target = typeof this.targetValue === 'string'
        ? parseFloat(this.targetValue) : this.targetValue;
      if (isNaN(target)) return;
      this.animate(this.currentValue, target);
    }
  }

  private animate(from: number, to: number): void {
    if (this.animationFrame) cancelAnimationFrame(this.animationFrame);

    const start = performance.now();
    const duration = this.countDuration;

    const step = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = from + (to - from) * eased;
      this.currentValue = current;
      this.el.nativeElement.textContent =
        `${this.countPrefix}${current.toFixed(this.countDecimals)}${this.countSuffix}`;

      if (progress < 1) {
        this.animationFrame = requestAnimationFrame(step);
      } else {
        this.currentValue = to;
        this.el.nativeElement.textContent =
          `${this.countPrefix}${to.toFixed(this.countDecimals)}${this.countSuffix}`;
      }
    };

    this.animationFrame = requestAnimationFrame(step);
  }
}
