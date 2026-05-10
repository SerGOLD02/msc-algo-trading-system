import {
  Component, OnInit, OnDestroy, ChangeDetectionStrategy,
  ChangeDetectorRef, inject
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Observable, Subject, takeUntil } from 'rxjs';
import { MarketService } from '../../core/services/market.service';
import { BacktestService } from '../../core/services/backtest.service';
import { AnalyticsService } from '../../core/services/analytics.service';
import { ExportService } from '../../core/services/export.service';
import { ThemeService } from '../../core/services/theme.service';
import { LanguageService } from '../../core/services/language.service';
import { TranslatePipe } from '../../shared/pipes/translate.pipe';
import { MarketSnapshot } from '../../core/models/market.model';
import {
  BacktestParams, BacktestResponse, RegimeStatus
} from '../../core/models/backtest.model';
import {
  WeeklySignalResponse, DecayHistoryResponse,
  CorrelationHeatmapResponse, DrawdownResponse,
  ChronosBandsResponse, OperationalStatus,
  YearlyBreakdownResponse, EtfPerformanceResponse,
  RegimeStatsResponse, WeeklyDecompositionResponse
} from '../../core/models/analytics.model';
import { TopTableComponent } from '../../shared/components/top-table/top-table.component';
import { EquityChartComponent } from '../../shared/components/equity-chart/equity-chart.component';
import { ParamSidebarComponent } from '../../shared/components/param-sidebar/param-sidebar.component';
import { CountdownComponent } from '../../shared/components/countdown/countdown.component';
import { SignalBlotterComponent } from '../../shared/components/signal-blotter/signal-blotter.component';
import { DecayChartComponent } from '../../shared/components/decay-chart/decay-chart.component';
import { ChronosBandsComponent } from '../../shared/components/chronos-bands/chronos-bands.component';
import { CorrelationHeatmapComponent } from '../../shared/components/correlation-heatmap/correlation-heatmap.component';
import { DrawdownGaugeComponent } from '../../shared/components/drawdown-gauge/drawdown-gauge.component';
import { InfoTooltipComponent } from '../../shared/components/info-tooltip/info-tooltip.component';
import { ToastContainerComponent } from '../../shared/components/toast-container/toast-container.component';
import { AllocationTreemapComponent } from '../../shared/components/allocation-treemap/allocation-treemap.component';
import { EtfGlossaryComponent } from '../../shared/components/etf-glossary/etf-glossary.component';
import { YearlyBreakdownComponent } from '../../shared/components/yearly-breakdown/yearly-breakdown.component';
import { OperationalStatusComponent } from '../../shared/components/operational-status/operational-status.component';
import { EtfPerformanceComponent } from '../../shared/components/etf-performance/etf-performance.component';
import { RegimeStatsComponent } from '../../shared/components/regime-stats/regime-stats.component';
import { WeeklyDecompositionComponent } from '../../shared/components/weekly-decomposition/weekly-decomposition.component';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    TopTableComponent,
    EquityChartComponent,
    ParamSidebarComponent,
    CountdownComponent,
    SignalBlotterComponent,
    DecayChartComponent,
    ChronosBandsComponent,
    CorrelationHeatmapComponent,
    DrawdownGaugeComponent,
    InfoTooltipComponent,
    ToastContainerComponent,
    AllocationTreemapComponent,
    EtfGlossaryComponent,
    YearlyBreakdownComponent,
    OperationalStatusComponent,
    EtfPerformanceComponent,
    RegimeStatsComponent,
    WeeklyDecompositionComponent,
    TranslatePipe
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();
  public langService = inject(LanguageService);

  snapshot: MarketSnapshot | null = null;
  defaultBacktest: BacktestResponse | null = null;
  customBacktest: BacktestResponse | null = null;
  regime: RegimeStatus | null = null;
  isLoadingCustom = false;
  secondsToFriday = 0;
  selectedPeriod: string = '2026-01-02';

  // New panel data
  signalData: WeeklySignalResponse | null = null;
  decayData: DecayHistoryResponse | null = null;
  correlationData: CorrelationHeatmapResponse | null = null;
  drawdownData: DrawdownResponse | null = null;
  chronosData: ChronosBandsResponse | null = null;
  yearlyData: YearlyBreakdownResponse | null = null;
  operationalStatus: OperationalStatus | null = null;
  etfPerformance: EtfPerformanceResponse | null = null;
  regimeStats: RegimeStatsResponse | null = null;
  weeklyDecomp: WeeklyDecompositionResponse | null = null;

  defaultParams: BacktestParams = {
    bet_quality: 0.50, hrp_alpha: 0.50,
    k_sigmoid: 10.0,  c_soglia: 0.50,
    k_up: 1.25,       k_down: 1.50,
  };

  constructor(
    private marketService: MarketService,
    private backtestService: BacktestService,
    private analyticsService: AnalyticsService,
    private cdr: ChangeDetectorRef,
    private toastService: ToastService,
    public exportService: ExportService,
    public themeService: ThemeService,
  ) {}

  ngOnInit(): void {
    this.secondsToFriday = this._computeSecondsToFriday();

    // Stream prezzi ogni 2 minuti
    this.marketService.snapshot$
      .pipe(takeUntil(this.destroy$))
      .subscribe(snap => {
        if (snap) {
          this.snapshot = snap;
          if (snap.seconds_to_friday_close > 0) {
            this.secondsToFriday = snap.seconds_to_friday_close;
          }
        }
        this.cdr.markForCheck();
      });

    this._sub(this.backtestService.getDefault(), bt => this.defaultBacktest = bt);

    // Regime HMM — special case: toast notification on regime change
    this.backtestService.getCurrentRegime()
      .pipe(takeUntil(this.destroy$))
      .subscribe(r => {
        if (this.regime && r && r.regime_id !== this.regime.regime_id) {
          const msg = r.is_crisis
            ? this.langService.translate('⚠️ Regime cambiato: CRISIS STATE attivo')
            : this.langService.translate('Regime aggiornato: ') + `Stato ${r.regime_id} (${r.regime_name})`;
          this.toastService.show(msg, r.is_crisis ? 'warning' : 'info');
        }
        this.regime = r;
        this.cdr.markForCheck();
      });

    this._sub(this.analyticsService.getWeeklySignals(), s => this.signalData = s);
    this._sub(this.analyticsService.getDecayHistory(), d => this.decayData = d);
    this._sub(this.analyticsService.getCorrelationHeatmap(), c => this.correlationData = c);
    this._sub(this.analyticsService.getDrawdown(), d => this.drawdownData = d);
    this._sub(this.analyticsService.getChronosBands(), c => this.chronosData = c);
    this._sub(this.analyticsService.getYearlyBreakdown(), y => this.yearlyData = y);
    this._sub(this.analyticsService.getOperationalStatus(), s => this.operationalStatus = s);
    this._sub(this.analyticsService.getEtfPerformance(), e => this.etfPerformance = e);
    this._sub(this.analyticsService.getRegimeStats(), r => this.regimeStats = r);
    this._sub(this.analyticsService.getWeeklyDecomposition(), w => this.weeklyDecomp = w);
  }

  onPeriodChanged(startDate: string): void {
    this.selectedPeriod = startDate;
    this.isLoadingCustom = true;
    this.cdr.markForCheck();

    // Reload default backtest with new period
    this._sub(this.backtestService.getDefault(startDate), bt => {
      this.defaultBacktest = bt;
      this.isLoadingCustom = false;
    });

    // Reload period-dependent analytics
    this._sub(this.analyticsService.getYearlyBreakdown(startDate), y => this.yearlyData = y);
    this._sub(this.analyticsService.getDecayHistory(startDate), d => this.decayData = d);
    this._sub(this.analyticsService.getDrawdown(startDate), d => this.drawdownData = d);
  }

  onParamsChanged(params: BacktestParams): void {
    // If params match defaults, clear custom line
    const d = this.defaultParams;
    if (params.bet_quality === d.bet_quality &&
        params.hrp_alpha === d.hrp_alpha &&
        params.k_sigmoid === d.k_sigmoid &&
        params.c_soglia === d.c_soglia &&
        params.k_up === d.k_up &&
        params.k_down === d.k_down) {
      this.customBacktest = null;
      this.isLoadingCustom = false;
      this.cdr.markForCheck();
      return;
    }

    this.isLoadingCustom = true;
    this.cdr.markForCheck();

    this.backtestService.compute(params, this.selectedPeriod !== '2026-01-02' ? this.selectedPeriod : undefined)
      .pipe(takeUntil(this.destroy$))
      .subscribe(bt => {
        this.customBacktest = bt;
        this.isLoadingCustom = false;
        this.cdr.markForCheck();
      });
  }

  onFridayChanged(friday: string): void {
    this.analyticsService.getWeeklySignals(friday)
      .pipe(takeUntil(this.destroy$))
      .subscribe(s => {
        this.signalData = s;
        this.cdr.markForCheck();
      });

    this.analyticsService.getChronosBands(friday)
      .pipe(takeUntil(this.destroy$))
      .subscribe(c => {
        this.chronosData = c;
        this.cdr.markForCheck();
      });
  }

  onChronosFridayChanged(friday: string): void {
    this.analyticsService.getChronosBands(friday)
      .pipe(takeUntil(this.destroy$))
      .subscribe(c => {
        this.chronosData = c;
        this.cdr.markForCheck();
      });
  }

  onAllocationFridayChanged(friday: string): void {
    this.analyticsService.getWeeklySignals(friday)
      .pipe(takeUntil(this.destroy$))
      .subscribe(s => {
        this.signalData = s;
        this.cdr.markForCheck();
      });
  }

  onCorrelationWindowChanged(window: string): void {
    this.analyticsService.getCorrelationHeatmap(window)
      .pipe(takeUntil(this.destroy$))
      .subscribe(c => {
        this.correlationData = c;
        this.cdr.markForCheck();
      });
  }

  private _sub<T>(obs$: Observable<T>, assign: (val: T) => void): void {
    obs$.pipe(takeUntil(this.destroy$)).subscribe(val => {
      assign(val);
      this.cdr.markForCheck();
    });
  }

  private _computeSecondsToFriday(): number {
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
    const etOffset = -4 * 3600000;
    const etNow = new Date(utcMs + etOffset);
    let daysAhead = (5 - etNow.getDay()) % 7;
    if (daysAhead === 0 && etNow.getHours() >= 16) daysAhead = 7;
    if (daysAhead === 0) daysAhead = 0;
    const target = new Date(etNow);
    target.setDate(target.getDate() + daysAhead);
    target.setHours(16, 0, 0, 0);
    return Math.max(0, Math.floor((target.getTime() - etNow.getTime()) / 1000));
  }

  get marketStatus(): { status: 'open' | 'closed' | 'pre-close'; time: string } {
    const now = new Date();
    const etOffset = this.isDST(now) ? -4 : -5;
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    const et = new Date(utc + etOffset * 3600000);

    const hours = et.getHours();
    const minutes = et.getMinutes();
    const day = et.getDay();
    const timeStr = `${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')} ET`;

    if (day >= 1 && day <= 5) {
      const minutesOfDay = hours * 60 + minutes;
      if (minutesOfDay >= 570 && minutesOfDay < 960) {
        if (day === 5 && minutesOfDay >= 930) {
          return { status: 'pre-close', time: timeStr };
        }
        return { status: 'open', time: timeStr };
      }
    }
    return { status: 'closed', time: timeStr };
  }

  private isDST(d: Date): boolean {
    const jan = new Date(d.getFullYear(), 0, 1).getTimezoneOffset();
    const jul = new Date(d.getFullYear(), 6, 1).getTimezoneOffset();
    return d.getTimezoneOffset() < Math.max(jan, jul);
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
