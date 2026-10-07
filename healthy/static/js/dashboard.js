/**
 * 바람길 (Baramgil) Precision Health Engine - Dashboard Controller
 * Dynamic Chart.js Rendering & Interactive Filtering Engine
 */

// Global Chart Instances
let bodyCompChart = null;
let workoutChart = null;
let clinicalChart = null;
let cachedBodyCompData = null;
let currentBodyCompView = 'all';
let currentWorkoutView = 'all';

// Current Filter State
const filterState = {
  days: 'all',
  sport: 'all',
  activeTab: 'workouts'
};

document.addEventListener('DOMContentLoaded', () => {
  initFilterControls();
  initTabNavigation();
  loadSummaryKPIs();
  renderBodyCompChart();
  renderWorkoutChart();
  renderClinicalChart();
  loadWorkoutsList();
  loadClinicalItemsTable();
});

/* ==========================================================================
   1. Filter & Tab Controls
   ========================================================================== */
function initFilterControls() {
  // Period Pills
  document.querySelectorAll('[data-filter-days]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('[data-filter-days]').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      filterState.days = e.target.getAttribute('data-filter-days');
      renderWorkoutChart();
      loadWorkoutsList();
    });
  });

  // Sport Pills
  document.querySelectorAll('[data-filter-sport]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('[data-filter-sport]').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      filterState.sport = e.target.getAttribute('data-filter-sport');
      renderWorkoutChart();
      loadWorkoutsList();
    });
  });
}

function initTabNavigation() {
  document.querySelectorAll('.nav-tab-btn').forEach(tabBtn => {
    tabBtn.addEventListener('click', (e) => {
      const targetId = e.currentTarget.getAttribute('data-target');
      document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
      e.currentTarget.classList.add('active');

      document.querySelectorAll('.tab-content-panel').forEach(panel => {
        panel.style.display = panel.id === targetId ? 'block' : 'none';
      });
      filterState.activeTab = targetId;
    });
  });
}

/* ==========================================================================
   2. KPI Summary Loader
   ========================================================================== */
async function loadSummaryKPIs() {
  try {
    const res = await fetch('/api/summary');
    const data = await res.json();
    if (data.status !== 'success') return;

    // Body Comp
    const b = data.body;
    document.getElementById('kpi-weight').textContent = b.weight_kg ? b.weight_kg.toFixed(1) : '--';
    document.getElementById('kpi-muscle').textContent = b.skeletal_muscle_kg ? b.skeletal_muscle_kg.toFixed(1) : '--';
    const muscleStatus = document.getElementById('kpi-muscle-status');
    if (muscleStatus) {
      muscleStatus.textContent = `★ ${b.muscle_line_status}`;
      muscleStatus.className = b.skeletal_muscle_kg >= 35.0 ? 'status-tag tag-success' : 'status-tag tag-warning';
    }
    const fatMassEl = document.getElementById('kpi-fat-mass');
    if (fatMassEl) fatMassEl.textContent = b.body_fat_kg ? b.body_fat_kg.toFixed(1) : '--';
    const fatPctEl = document.getElementById('kpi-fat-pct');
    if (fatPctEl) fatPctEl.textContent = b.body_fat_pct ? b.body_fat_pct.toFixed(1) : '--';

    const bodyDate = document.getElementById('kpi-body-date');
    if (bodyDate) bodyDate.textContent = `${b.date || ''} 측정 (BMI ${b.bmi || '--'}, 체지방 ${b.body_fat_pct || '--'}%)`;

    // Week Stats
    const w = data.week;
    document.getElementById('kpi-week-distance').textContent = w.distance_km ? w.distance_km.toFixed(1) : '0.0';
    document.getElementById('kpi-week-kcal').textContent = w.total_kcal ? w.total_kcal.toLocaleString() : '0';
    document.getElementById('kpi-week-sessions').textContent = `${w.active_days}일 / ${w.session_count}세션 (${w.duration_minutes}분)`;

    // Total Stats
    const t = data.total;
    document.getElementById('kpi-total-dist').textContent = `${t.distance_km} km`;
    document.getElementById('kpi-total-kcal').textContent = `${t.total_kcal.toLocaleString()} kcal`;
    document.getElementById('kpi-total-period').textContent = t.period;

    // Clinical D-Day & Fasting Blood Sugar
    const c = data.clinical;
    document.getElementById('kpi-exam-dday').textContent = `D-${c.d_day}`;
    document.getElementById('kpi-exam-target-date').textContent = `${c.target_date} (4분기 정기검진)`;

    const fbsValEl = document.getElementById('kpi-fbs-val');
    const fbsDateEl = document.getElementById('kpi-fbs-date');
    if (data.fasting_blood_sugar) {
      if (fbsValEl) fbsValEl.textContent = data.fasting_blood_sugar.glucose;
      if (fbsDateEl) fbsDateEl.textContent = `${data.fasting_blood_sugar.date.substring(5)} 측정`;
    } else {
      if (fbsValEl) fbsValEl.textContent = '--';
      if (fbsDateEl) fbsDateEl.textContent = '기록 없음';
    }

    const examSummaryEl = document.getElementById('kpi-exam-latest-summary');
    if (examSummaryEl) {
      examSummaryEl.textContent = `피검사 기준 (${c.exam_date}): HbA1c ${c.hba1c}% | 공복 ${c.glucose || 111} | TG ${c.tg} | 요산 ${c.uric_acid}`;
    }

  } catch (err) {
    console.error('Failed to load KPIs:', err);
  }
}

/* ==========================================================================
   3. Chart.js Implementations
   ========================================================================== */

// Chart Global Dark Theme Defaults
if (typeof Chart !== 'undefined') {
  Chart.defaults.color = '#94A3B8';
  Chart.defaults.font.family = "'Pretendard', sans-serif";
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.95)';
  Chart.defaults.plugins.tooltip.titleColor = '#F8FAFC';
  Chart.defaults.plugins.tooltip.bodyColor = '#E2E8F0';
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.15)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

// 3.1 Body Composition Chart (체중 vs 골격근량 vs 체지방량 3대 복합 / 단독 선택 지원)
async function renderBodyCompChart() {
  const ctx = document.getElementById('bodyCompChartCanvas');
  if (!ctx) return;

  try {
    const res = await fetch('/api/chart/body-comp');
    const data = await res.json();
    if (data.status !== 'success') return;
    cachedBodyCompData = data;
    updateBodyCompSummary(data);

    if (bodyCompChart) bodyCompChart.destroy();

    bodyCompChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: '골격근량 (kg)',
            data: data.muscles,
            borderColor: '#10B981',
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            borderWidth: 3,
            pointBackgroundColor: '#10B981',
            pointRadius: 5,
            pointHoverRadius: 7,
            yAxisID: 'yMuscle',
            tension: 0.25,
            fill: false
          },
          {
            label: '체지방량 (kg)',
            data: data.fat_masses,
            borderColor: '#F43F5E',
            backgroundColor: 'rgba(244, 63, 94, 0.12)',
            borderWidth: 2.5,
            pointBackgroundColor: '#F43F5E',
            pointRadius: 4,
            pointHoverRadius: 6,
            yAxisID: 'yFat',
            tension: 0.25,
            fill: false
          },
          {
            label: '체중 (kg)',
            data: data.weights,
            borderColor: '#38BDF8',
            backgroundColor: 'rgba(56, 189, 248, 0.08)',
            borderWidth: 2,
            pointBackgroundColor: '#38BDF8',
            pointRadius: 4,
            pointHoverRadius: 6,
            yAxisID: 'yWeight',
            tension: 0.25,
            fill: false
          },
          {
            label: '35.0kg 골격근량 사수선',
            data: data.target_muscle_line,
            borderColor: '#F59E0B',
            borderWidth: 2,
            borderDash: [5, 4],
            pointRadius: 0,
            fill: false,
            yAxisID: 'yMuscle'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: { font: { size: 11 } }
          },
          yMuscle: {
            type: 'linear',
            position: 'left',
            min: 34.0,
            max: 36.5,
            title: { display: true, text: '골격근 (kg)', color: '#10B981', font: { weight: 'bold' } },
            grid: { color: 'rgba(255, 255, 255, 0.05)' }
          },
          yFat: {
            type: 'linear',
            position: 'left',
            min: 13.5,
            max: 18.0,
            title: { display: true, text: '체지방 (kg)', color: '#F43F5E', font: { weight: 'bold' } },
            grid: { drawOnChartArea: false }
          },
          yWeight: {
            type: 'linear',
            position: 'right',
            min: 75.0,
            max: 80.0,
            title: { display: true, text: '체중 (kg)', color: '#38BDF8', font: { weight: 'bold' } },
            grid: { drawOnChartArea: false }
          }
        },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 12,
              font: { size: 12 },
              filter: function(item, chartData) {
                if (currentBodyCompView === 'all') return true;
                return !chartData.datasets[item.datasetIndex].hidden;
              }
            }
          },
          tooltip: {
            callbacks: {
              afterLabel: function(context) {
                if (context.dataset.label && context.dataset.label.includes('체지방량')) {
                  const idx = context.dataIndex;
                  const pct = data.fat_pcts ? data.fat_pcts[idx] : null;
                  return pct ? `(체지방률: ${pct.toFixed(1)}%)` : '';
                }
                return null;
              }
            }
          }
        }
      }
    });

    initBodyCompViewControls();
    if (currentBodyCompView !== 'all') {
      applyBodyCompView(currentBodyCompView);
    }
  } catch (err) {
    console.error('Error rendering BodyCompChart:', err);
  }
}

function initBodyCompViewControls() {
  document.querySelectorAll('#bodycomp-toggle-group [data-bodycomp-view]').forEach(btn => {
    btn.onclick = (e) => {
      const view = e.currentTarget.getAttribute('data-bodycomp-view');
      applyBodyCompView(view);
    };
  });

  document.querySelectorAll('.target-legend-item[data-legend-for]').forEach(el => {
    el.onclick = (e) => {
      const target = e.currentTarget.getAttribute('data-legend-for');
      if (currentBodyCompView === target) {
        applyBodyCompView('all');
      } else {
        applyBodyCompView(target);
      }
    };
  });
}

function applyBodyCompView(view) {
  if (!bodyCompChart) return;
  currentBodyCompView = view;

  document.querySelectorAll('#bodycomp-toggle-group [data-bodycomp-view]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-bodycomp-view') === view);
  });

  const badge = document.getElementById('bodyCompChartBadge');
  const datasets = bodyCompChart.data.datasets;
  const scales = bodyCompChart.options.scales;

  if (view === 'all') {
    if (badge) badge.textContent = '3대 복합 축';
    datasets[0].hidden = false; // 골격근량
    datasets[1].hidden = false; // 체지방량
    datasets[2].hidden = false; // 체중
    datasets[3].hidden = false; // 35.0kg 사수선

    scales.yMuscle.display = true;
    scales.yMuscle.position = 'left';
    scales.yMuscle.grid.drawOnChartArea = true;

    scales.yFat.display = true;
    scales.yFat.position = 'left';
    scales.yFat.grid.drawOnChartArea = false;

    scales.yWeight.display = true;
    scales.yWeight.position = 'right';
    scales.yWeight.grid.drawOnChartArea = false;
  } else if (view === 'muscle') {
    if (badge) badge.textContent = '골격근 단독 축';
    datasets[0].hidden = false;
    datasets[1].hidden = true;
    datasets[2].hidden = true;
    datasets[3].hidden = false;

    scales.yMuscle.display = true;
    scales.yMuscle.position = 'left';
    scales.yMuscle.grid.drawOnChartArea = true;

    scales.yFat.display = false;
    scales.yWeight.display = false;
  } else if (view === 'fat') {
    if (badge) badge.textContent = '체지방 단독 축';
    datasets[0].hidden = true;
    datasets[1].hidden = false;
    datasets[2].hidden = true;
    datasets[3].hidden = true;

    scales.yMuscle.display = false;

    scales.yFat.display = true;
    scales.yFat.position = 'left';
    scales.yFat.grid.drawOnChartArea = true;

    scales.yWeight.display = false;
  } else if (view === 'weight') {
    if (badge) badge.textContent = '체중 단독 축';
    datasets[0].hidden = true;
    datasets[1].hidden = true;
    datasets[2].hidden = false;
    datasets[3].hidden = true;

    scales.yMuscle.display = false;
    scales.yFat.display = false;

    scales.yWeight.display = true;
    scales.yWeight.position = 'left';
    scales.yWeight.grid.drawOnChartArea = true;
  }

  document.querySelectorAll('#panel-body-comp-chart .target-legend-item[data-legend-for]').forEach(el => {
    const target = el.getAttribute('data-legend-for');
    if (view === 'all' || target === view) {
      el.style.opacity = '1';
    } else {
      el.style.opacity = '0.35';
    }
  });

  bodyCompChart.update();
}

/**
 * 체성분 전용 한줄평 브리핑 생성 (임선우 코치)
 */
function updateBodyCompSummary(data) {
  const textEl = document.getElementById('bodycompSummaryText');
  if (!textEl || !data || !data.muscles || data.muscles.length === 0) return;

  const validMuscles = data.muscles.filter(v => v !== null && v !== undefined);
  const validWeights = data.weights.filter(v => v !== null && v !== undefined);
  const validFats = data.fat_masses.filter(v => v !== null && v !== undefined);

  if (validMuscles.length === 0) return;

  const latestMuscle = validMuscles[validMuscles.length - 1];
  const latestWeight = validWeights[validWeights.length - 1];
  const latestFat = validFats[validFats.length - 1];

  let summaryHtml = '';

  if (latestMuscle >= 35.0) {
    if (validMuscles.length >= 2) {
      const prevMuscle = validMuscles[validMuscles.length - 2];
      const diff = (latestMuscle - prevMuscle).toFixed(2);
      const sign = diff >= 0 ? `+${diff}` : `${diff}`;
      summaryHtml = `골격근량 <strong>${latestMuscle}kg</strong>(사수선 35.0kg 유지, 직전 대비 ${sign}kg) 및 체중 <strong>${latestWeight}kg</strong>로 견고한 근육량 방어와 이상적인 신체 밸런스를 입증하고 있습니다.`;
    } else {
      summaryHtml = `골격근량 <strong>${latestMuscle}kg</strong>(사수선 35.0kg 초과 달성) 및 체중 <strong>${latestWeight}kg</strong>로 최상의 근육량 방어 상태를 완벽히 유지하고 있습니다.`;
    }
  } else {
    summaryHtml = `골격근량 <strong>${latestMuscle}kg</strong>로 35.0kg 마지노선 경계 구간입니다. 과도한 유산소 소모를 조절하고 우유/라떼 및 단백질 영양 보충에 집중하시길 권장합니다.`;
  }

  textEl.innerHTML = summaryHtml;
}

// 3.2 Workout Load & Intensity Chart (칼로리 바 + 심박수 라인 복합 / 단독 선택 지원)
async function renderWorkoutChart() {
  const ctx = document.getElementById('workoutChartCanvas');
  if (!ctx) return;

  try {
    const query = new URLSearchParams({ days: filterState.days, sport: filterState.sport }).toString();
    const res = await fetch(`/api/chart/workouts?${query}`);
    const data = await res.json();
    if (data.status !== 'success') return;
    updateWorkoutSummary(data);

    if (workoutChart) workoutChart.destroy();

    // 600 kcal 오버트레이닝 기준선
    const overtrainLine = data.dates.map(() => 600);

    workoutChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            type: 'line',
            label: '평균 심박수 (BPM)',
            data: data.avg_hrs,
            borderColor: '#F43F5E',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointBackgroundColor: '#F43F5E',
            pointRadius: 4,
            yAxisID: 'yHR',
            tension: 0.3
          },
          {
            type: 'line',
            label: '과다 제동 기준선 (600 kcal)',
            data: overtrainLine,
            borderColor: '#F59E0B',
            borderWidth: 1.5,
            borderDash: [6, 4],
            pointRadius: 0,
            yAxisID: 'yKcal'
          },
          {
            type: 'bar',
            label: '총 소모 칼로리 (kcal)',
            data: data.total_kcals,
            backgroundColor: data.total_kcals.map(k => k > 600 ? 'rgba(239, 68, 68, 0.7)' : 'rgba(16, 185, 129, 0.65)'),
            borderRadius: 6,
            yAxisID: 'yKcal'
          },
          {
            type: 'bar',
            label: '이동 거리 (km)',
            data: data.distances,
            backgroundColor: 'rgba(6, 182, 212, 0.65)',
            borderRadius: 6,
            yAxisID: 'yDist'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: { font: { size: 10 }, maxRotation: 45 }
          },
          yKcal: {
            type: 'linear',
            position: 'left',
            min: 0,
            max: 1000,
            title: { display: true, text: '칼로리 (kcal)', color: '#10B981' },
            grid: { color: 'rgba(255, 255, 255, 0.05)' }
          },
          yHR: {
            type: 'linear',
            position: 'right',
            min: 80,
            max: 160,
            title: { display: true, text: '심박수 (BPM)', color: '#F43F5E' },
            grid: { drawOnChartArea: false }
          },
          yDist: {
            type: 'linear',
            position: 'right',
            display: false,
            min: 0,
            title: { display: true, text: '거리 (km)', color: '#06B6D4' },
            grid: { drawOnChartArea: false }
          }
        },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 12,
              font: { size: 11 },
              filter: function(item, chartData) {
                if (currentWorkoutView === 'all') return true;
                return !chartData.datasets[item.datasetIndex].hidden;
              }
            }
          }
        }
      }
    });

    initWorkoutViewControls();
    if (currentWorkoutView !== 'all') {
      applyWorkoutView(currentWorkoutView);
    }
  } catch (err) {
    console.error('Error rendering WorkoutChart:', err);
  }
}

function initWorkoutViewControls() {
  document.querySelectorAll('#workout-toggle-group [data-workout-view]').forEach(btn => {
    btn.onclick = (e) => {
      const view = e.currentTarget.getAttribute('data-workout-view');
      applyWorkoutView(view);
    };
  });

  document.querySelectorAll('#panel-workout-chart .target-legend-item[data-legend-for]').forEach(el => {
    el.onclick = (e) => {
      const target = e.currentTarget.getAttribute('data-legend-for');
      if (currentWorkoutView === target) {
        applyWorkoutView('all');
      } else {
        applyWorkoutView(target);
      }
    };
  });
}

function applyWorkoutView(view) {
  if (!workoutChart) return;
  currentWorkoutView = view;

  document.querySelectorAll('#workout-toggle-group [data-workout-view]').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-workout-view') === view);
  });

  const badge = document.getElementById('workoutChartBadge');
  const datasets = workoutChart.data.datasets;
  const scales = workoutChart.options.scales;

  // datasets: 0=평균심박수, 1=600kcal선, 2=총소모칼로리, 3=이동거리
  if (view === 'all') {
    if (badge) badge.textContent = '부하 복합 분석';
    datasets[0].hidden = false; // 심박수
    datasets[1].hidden = false; // 기준선
    datasets[2].hidden = false; // 칼로리
    datasets[3].hidden = false; // 거리

    scales.yKcal.display = true;
    scales.yKcal.position = 'left';
    scales.yKcal.grid.drawOnChartArea = true;

    scales.yHR.display = true;
    scales.yHR.position = 'right';
    scales.yHR.grid.drawOnChartArea = false;

    scales.yDist.display = false;
  } else if (view === 'kcal') {
    if (badge) badge.textContent = '소모 칼로리 단독';
    datasets[0].hidden = true;  // 심박수 숨김
    datasets[1].hidden = false; // 기준선 유지
    datasets[2].hidden = false; // 칼로리 유지
    datasets[3].hidden = true;  // 거리 숨김

    scales.yKcal.display = true;
    scales.yKcal.position = 'left';
    scales.yKcal.grid.drawOnChartArea = true;

    scales.yHR.display = false;
    scales.yDist.display = false;
  } else if (view === 'hr') {
    if (badge) badge.textContent = '평균 심박수 단독';
    datasets[0].hidden = false; // 심박수
    datasets[1].hidden = true;  // 기준선 숨김
    datasets[2].hidden = true;  // 칼로리 숨김
    datasets[3].hidden = true;  // 거리 숨김

    scales.yKcal.display = false;

    scales.yHR.display = true;
    scales.yHR.position = 'left';
    scales.yHR.grid.drawOnChartArea = true;

    scales.yDist.display = false;
  } else if (view === 'dist') {
    if (badge) badge.textContent = '이동 거리 단독';
    datasets[0].hidden = true;  // 심박수 숨김
    datasets[1].hidden = true;  // 기준선 숨김
    datasets[2].hidden = true;  // 칼로리 숨김
    datasets[3].hidden = false; // 거리 표시

    scales.yKcal.display = false;
    scales.yHR.display = false;

    scales.yDist.display = true;
    scales.yDist.position = 'left';
    scales.yDist.grid = { color: 'rgba(255, 255, 255, 0.05)', drawOnChartArea: true };
  }

  document.querySelectorAll('#panel-workout-chart .target-legend-item[data-legend-for]').forEach(el => {
    const target = el.getAttribute('data-legend-for');
    if (view === 'all' || target === view) {
      el.style.opacity = '1';
    } else {
      el.style.opacity = '0.35';
    }
  });

  workoutChart.update();
}

/**
 * 유산소 운동부하 전용 한줄평 브리핑 생성 (임선우 코치)
 */
function updateWorkoutSummary(data) {
  const textEl = document.getElementById('workoutSummaryText');
  if (!textEl || !data || !data.total_kcals || data.total_kcals.length === 0) return;

  const validKcals = data.total_kcals.filter(v => v !== null && v > 0);
  const validDistances = (data.distances || []).filter(v => v !== null && v > 0);
  const validHrs = (data.avg_hrs || []).filter(v => v !== null && v > 0);

  if (validKcals.length === 0) return;

  const latestKcal = validKcals[validKcals.length - 1];
  const latestDist = validDistances.length > 0 ? validDistances[validDistances.length - 1] : 0;
  const latestHr = validHrs.length > 0 ? validHrs[validHrs.length - 1] : 0;

  let summaryHtml = '';

  if (latestKcal > 600) {
    summaryHtml = `⚠️ <strong>[과다 제동 경계]</strong> 최근 세션 소모 칼로리(<strong>${latestKcal} kcal</strong>)가 600kcal 기준을 초과했습니다. 신장 사구체 보호를 위해 미온수 1L 보충 및 강제 휴식 전환이 필수적입니다!`;
  } else if (latestKcal >= 300) {
    const hrNotice = latestHr > 0 ? ` · 평균 심박 <strong>${latestHr} BPM</strong>` : '';
    const distNotice = latestDist > 0 ? ` <strong>${latestDist}km</strong> 완주` : '';
    summaryHtml = `🟢 <strong>[적정 부하 달성]</strong> 최근 세션${distNotice}(소모 <strong>${latestKcal} kcal</strong>${hrNotice})으로 Zone 2 유산소 목표를 완벽 달성하며 지방 연소와 심폐 혈관 탄력을 극대화했습니다.`;
  } else {
    const distNotice = latestDist > 0 ? ` (${latestDist}km)` : '';
    summaryHtml = `🔵 <strong>[회복 및 웜업 세션]</strong> 최근 세션${distNotice} 소모 <strong>${latestKcal} kcal</strong>로 관절과 신장 부담 없는 가벼운 액티브 리커버리 및 대사 순환 세션이 완료되었습니다.`;
  }

  textEl.innerHTML = summaryHtml;
}

// 3.3 Clinical Lab Results Chart (피검사 4대 KPI 시계열 + 목표선)
async function renderClinicalChart() {
  const ctx = document.getElementById('clinicalChartCanvas');
  if (!ctx) return;

  try {
    const res = await fetch('/api/chart/clinical');
    const data = await res.json();
    if (data.status !== 'success') return;

    if (clinicalChart) clinicalChart.destroy();

    clinicalChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: '당화혈색소 HbA1c (%) [목표 ≤5.5%]',
            data: data.hba1c,
            borderColor: '#10B981',
            backgroundColor: 'transparent',
            borderWidth: 3,
            pointBackgroundColor: '#10B981',
            pointRadius: 6,
            yAxisID: 'yPct',
            tension: 0.2
          },
          {
            label: '요산 Uric Acid (mg/dL) [목표 ≤6.50]',
            data: data.uric_acid,
            borderColor: '#F59E0B',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointBackgroundColor: '#F59E0B',
            pointRadius: 6,
            yAxisID: 'yPct',
            tension: 0.2
          },
          {
            label: '공복혈당 Glucose (mg/dL) [목표 ≤95]',
            data: data.glucose,
            borderColor: '#EF4444',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointBackgroundColor: '#EF4444',
            pointRadius: 6,
            yAxisID: 'yMgdl',
            tension: 0.2
          },
          {
            label: '중성지방 TG (mg/dL) [목표 ≤120]',
            data: data.tg,
            borderColor: '#8B5CF6',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointBackgroundColor: '#8B5CF6',
            pointRadius: 6,
            yAxisID: 'yMgdl',
            tension: 0.2
          },
          {
            label: 'LDL 콜레스테롤 (mg/dL) [최적 70~80]',
            data: data.ldl,
            borderColor: '#06B6D4',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointBackgroundColor: '#06B6D4',
            pointRadius: 6,
            yAxisID: 'yMgdl',
            tension: 0.2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { font: { weight: 'bold' } }
          },
          yPct: {
            type: 'linear',
            position: 'left',
            min: 4.5,
            max: 9.0,
            title: { display: true, text: '당화혈색소(%) / 요산(mg/dL)', color: '#10B981' },
            grid: { color: 'rgba(255, 255, 255, 0.05)' }
          },
          yMgdl: {
            type: 'linear',
            position: 'right',
            min: 50,
            max: 250,
            title: { display: true, text: '지질 지표 (mg/dL)', color: '#8B5CF6' },
            grid: { drawOnChartArea: false }
          }
        },
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 14, font: { size: 12 } } }
        }
      }
    });
  } catch (err) {
    console.error('Error rendering ClinicalChart:', err);
  }
}

/* ==========================================================================
   4. Workout History List Loader (Accordion)
   ========================================================================== */
async function loadWorkoutsList() {
  const container = document.getElementById('workoutListContainer');
  if (!container) return;

  try {
    const query = new URLSearchParams({ days: filterState.days, sport: filterState.sport }).toString();
    const res = await fetch(`/api/workouts?${query}`);
    const data = await res.json();
    if (data.status !== 'success') return;

    if (!data.workouts || data.workouts.length === 0) {
      container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-dim);">해당 조건의 운동 기록이 없습니다.</div>';
      return;
    }

    container.innerHTML = data.workouts.map((w, idx) => {
      const isFirst = idx === 0 ? 'open' : '';
      const evalTagClass = w.evaluation.includes('적정') ? 'tag-success' : 'tag-warning';
      
      const bodyCompBadge = w.body_comp ? `
        <span class="status-tag tag-info" title="샤워 후 체성분 측정">
          ⚖️ ${w.body_comp.weight_kg}kg | 근육 ${w.body_comp.skeletal_muscle_kg}kg (${w.body_comp.body_fat_pct}%)
        </span>
      ` : '';

      const fbsBadge = w.fasting_blood_sugar ? `
        <span class="status-tag" style="background: rgba(239, 68, 68, 0.18); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.35); font-weight: 600;" title="기상 직후 공복혈당 측정치">
          🩸 기상혈당 ${w.fasting_blood_sugar} mg/dL
        </span>
      ` : '';

      const sessionsHtml = w.sessions.map((s, sIdx) => {
        const splitsHtml = (s.splits && s.splits.length > 0) ? `
          <table class="splits-table">
            <thead>
              <tr>
                <th>구간</th>
                <th>거리</th>
                <th>시간</th>
                <th>속도/페이스</th>
                <th>심박수</th>
              </tr>
            </thead>
            <tbody>
              ${s.splits.map(sp => `
                <tr>
                  <td>Split ${sp.split_no}</td>
                  <td>${sp.distance_km ? sp.distance_km + 'km' : '--'}</td>
                  <td>${sp.time_str || '--'}</td>
                  <td>${sp.speed_kmh ? sp.speed_kmh + ' km/h' : '--'}</td>
                  <td>${sp.heart_rate_bpm ? sp.heart_rate_bpm + ' BPM' : '--'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        ` : '';

        return `
          <div class="session-box">
            <div class="session-title-bar">
              <span class="session-name">세션 ${s.session_no}. ${s.name}</span>
              <span class="status-tag ${s.sport_type.includes('자전거') ? 'tag-info' : 'tag-success'}">
                ${s.sport_type}
              </span>
            </div>
            <div class="session-stat-grid">
              <div class="stat-item">
                <span>운동 시간</span>
                <strong>${s.duration_str}</strong>
              </div>
              <div class="stat-item">
                <span>이동 거리</span>
                <strong>${s.distance_km} km ${s.estimated_distance_km ? '(보정 ' + s.estimated_distance_km + 'k)' : ''}</strong>
              </div>
              <div class="stat-item">
                <span>소모 칼로리</span>
                <strong>${s.total_kcal} kcal</strong>
              </div>
              <div class="stat-item">
                <span>평균 심박</span>
                <strong>${s.avg_heart_rate_bpm ? s.avg_heart_rate_bpm + ' BPM' : '--'}</strong>
              </div>
              <div class="stat-item">
                <span>상승 고도</span>
                <strong>${s.elevation_gain_m} m</strong>
              </div>
              <div class="stat-item">
                <span>운동 강도</span>
                <strong>${s.effort || '--'}</strong>
              </div>
            </div>
            ${s.notes ? `<div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.4rem;">💡 ${s.notes}</div>` : ''}
            ${splitsHtml}
          </div>
        `;
      }).join('');

      const dayMap = {
        Mon: '월요일',
        Tue: '화요일',
        Wed: '수요일',
        Thu: '목요일',
        Fri: '금요일',
        Sat: '토요일',
        Sun: '일요일',
        월: '월요일',
        화: '화요일',
        수: '수요일',
        목: '목요일',
        금: '금요일',
        토: '토요일',
        일: '일요일'
      };
      const dayName = dayMap[w.day_of_week] || (w.day_of_week ? (w.day_of_week.endsWith('요일') ? w.day_of_week : `${w.day_of_week}요일`) : '');

      return `
        <div class="workout-day-card ${isFirst}" id="workout-card-${w.id}">
          <div class="workout-day-header" onclick="toggleWorkoutCard('${w.id}')">
            <div class="workout-day-info">
              <span class="workout-date-badge">${w.date}</span>
              <span class="workout-day-name">${dayName}</span>
              <span class="workout-routine-tag">${w.routine_name || w.workout_type}</span>
              <span class="status-tag ${evalTagClass}">${w.evaluation}</span>
              ${bodyCompBadge}
              ${fbsBadge}
            </div>
            <div class="workout-metrics-summary">
              <div class="metric-pill">
                <span>시간:</span> <strong>${w.summary.total_duration_str}</strong>
              </div>
              <div class="metric-pill">
                <span>거리:</span> <strong>${w.summary.total_distance_km} km</strong>
              </div>
              <div class="metric-pill">
                <span>칼로리:</span> <strong>${w.summary.total_kcal} kcal</strong>
              </div>
              <span class="chevron-icon">▼</span>
            </div>
          </div>
          <div class="workout-day-body">
            ${w.notes ? `
              <div class="coaching-quote-box">
                <div class="coaching-author">🩺 임상 코칭 피드백 & 데일리 요약 (개발4팀 임선우 수석 튜터)</div>
                <div>${w.notes}</div>
              </div>
            ` : ''}
            <div class="sessions-subgrid">
              ${sessionsHtml}
            </div>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading workouts list:', err);
  }
}

function toggleWorkoutCard(id) {
  const card = document.getElementById(`workout-card-${id}`);
  if (card) {
    card.classList.toggle('open');
  }
}

/* ==========================================================================
   5. Clinical Items Table Loader (33개 항목 전수)
   ========================================================================== */
async function loadClinicalItemsTable() {
  const tbody = document.getElementById('clinicalTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/clinical/items');
    const data = await res.json();
    if (data.status !== 'success') return;

    tbody.innerHTML = data.items.map(item => {
      const isKpi = ['HbA1c (당화혈색소)', 'Glucose (혈당)', 'Triglyceride (중성지방)', 'Uric Acid (요산)', 'LDL-cholesterol (저밀도)', 'Creatinine (크레아티닌)'].includes(item.name);
      const rowClass = isKpi ? 'kpi-row' : '';

      return `
        <tr class="${rowClass}">
          <td><span class="status-tag tag-info" style="font-size:0.7rem;">${item.category}</span></td>
          <td class="highlight-val">${item.name}</td>
          <td>${item.values['2026-02-23'] || '-'}</td>
          <td>${item.values['2026-04-02'] || '-'}</td>
          <td>${item.values['2026-05-19'] || '-'}</td>
          <td style="color: var(--primary-light); font-weight: 700;">${item.values['2026-08-18'] || '-'}</td>
          <td><small>${item.reference} ${item.unit}</small></td>
          <td style="color: var(--text-muted); font-size: 0.8rem;">${item.evaluation || '-'}</td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading clinical items table:', err);
  }
}
