import { Injectable, signal } from '@angular/core';
import { IT, EN } from '../utils/translations';

export type Lang = 'it' | 'en';

@Injectable({ providedIn: 'root' })
export class LanguageService {
  private _lang = signal<Lang>(this.loadLang());
  lang = this._lang.asReadonly();

  toggle(): void {
    const next: Lang = this._lang() === 'it' ? 'en' : 'it';
    this._lang.set(next);
    localStorage.setItem('lang', next);
  }

  translate(key: string): string {
    const dict = this._lang() === 'it' ? IT : EN;
    return dict[key] ?? key;
  }

  private loadLang(): Lang {
    const stored = localStorage.getItem('lang');
    return (stored === 'en' || stored === 'it') ? stored : 'it';
  }
}
