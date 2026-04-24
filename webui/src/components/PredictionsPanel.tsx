import { Button, Empty } from 'antd';
import { HolderOutlined } from '@ant-design/icons';
import type { Prediction } from '../types';
import styles from '../styles/components/predictionsPanel.module.css';

interface PredictionsPanelProps {
  predictions: Prediction[];
  onClear: () => void;
  onDragStart: (prediction: Prediction) => void;
}

export default function PredictionsPanel({
  predictions,
  onClear,
  onDragStart,
}: PredictionsPanelProps) {
  const handleDragStart = (prediction: Prediction, e: React.DragEvent) => {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('prediction', JSON.stringify(prediction));
    onDragStart(prediction);
  };

  const sourcePredictions = predictions.filter(p => p.source === 'source');
  const destPredictions = predictions.filter(p => p.source === 'dest');

  const renderPredictionColumn = (title: string, preds: Prediction[]) => {
    if (preds.length === 0) {
      return (
        <div className={styles.column}>
          <div className={styles.columnHeader}>{title}</div>
          <Empty
            description="No predictions"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </div>
      );
    }

    return (
      <div className={styles.column}>
        <div className={styles.columnHeader}>{title} ({preds.length})</div>
        <div className={styles.predictionsList}>
          {preds.map((prediction, idx) => (
            <div
              key={idx}
              className={styles.predictionItem}
              draggable
              onDragStart={(e) => handleDragStart(prediction, e)}
            >
              <div>
                <span className={styles.ipText}>
                  {prediction.ip.original}
                  {prediction.hostname && (
                    <span className={styles.hostnameText}>
                      {' ('}{prediction.hostname}{')'}
                    </span>
                  )}
                </span>
                <span className={styles.candidatesText}>
                  → {prediction.candidates.map((c, i) => (
                    <span key={i}>
                      <strong>{c.domain.name}</strong> {c.package.name}
                    </span>
                  )).reduce((prev, curr) => (
                    <>{prev} | {curr}</>
                  ), null as any)}
                </span>
              </div>
              <HolderOutlined className={styles.dragHandle} />
            </div>
          ))}
        </div>
      </div>
    );
  };

  if (predictions.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.header}>
          <span className={styles.title}>PREDICTIONS</span>
        </div>
        <Empty
          description="Add IPs to see matching domains and packages"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>PREDICTIONS</span>
        <Button size="small" onClick={onClear}>
          Clear
        </Button>
      </div>
      <div className={styles.twoColumns}>
        {renderPredictionColumn('SOURCE', sourcePredictions)}
        {renderPredictionColumn('DESTINATION', destPredictions)}
      </div>
    </div>
  );
}
