import { Injectable } from '@angular/core';
import { ToastService } from './toast.service';

@Injectable({ providedIn: 'root' })
export class ExportService {
  constructor(private toast: ToastService) {}

  async exportDashboardPdf(): Promise<void> {
    this.toast.info('Generazione PDF in corso...');

    try {
      const html2canvas = (await import('html2canvas')).default;
      const { jsPDF } = await import('jspdf');

      const dashEl = document.querySelector('.dashboard-layout') as HTMLElement;
      if (!dashEl) {
        this.toast.error('Elemento dashboard non trovato');
        return;
      }

      const canvas = await html2canvas(dashEl, {
        scale: 1.5,
        useCORS: true,
        logging: false,
        backgroundColor: getComputedStyle(document.documentElement)
          .getPropertyValue('--color-bg').trim() || '#fafafa',
      });

      const imgData = canvas.toDataURL('image/png');
      const imgW = canvas.width;
      const imgH = canvas.height;

      // A4 landscape
      const pdf = new jsPDF({
        orientation: imgW > imgH ? 'landscape' : 'portrait',
        unit: 'px',
        format: [imgW, imgH],
      });

      pdf.addImage(imgData, 'PNG', 0, 0, imgW, imgH);

      const now = new Date();
      const dateStr = now.toISOString().split('T')[0];
      pdf.save(`trading_dashboard_report_${dateStr}.pdf`);

      this.toast.success('PDF generato con successo!');
    } catch (err) {
      console.error('PDF export error:', err);
      this.toast.error('Errore nella generazione del PDF');
    }
  }
}
