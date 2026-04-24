import { Button, Empty } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useEffect, useCallback } from 'react';
import RuleCard from './RuleCard';
import type { RuleCard as RuleCardType, IpEntry, DomainItem, PackageItem, SectionItem } from '../types';
import styles from '../styles/components/cardsContainer.module.css';

interface CardsContainerProps {
  cards: RuleCardType[];
  sourcePool: IpEntry[];
  destPool: IpEntry[];
  domains: DomainItem[];
  packages: PackageItem[];
  sections: SectionItem[];
  selectedCardId: string | null;
  onCardsChange: (cards: RuleCardType[]) => void;
  onSelectedCardIdChange: (id: string | null) => void;
  onFetchPackages: (domainUid: string) => void;
  onFetchSections: (domainUid: string, pkgUid: string) => void;
  onSubmit: () => void;
  submitting: boolean;
}

export default function CardsContainer({
  cards,
  sourcePool,
  destPool,
  domains,
  packages,
  sections,
  selectedCardId,
  onCardsChange,
  onSelectedCardIdChange,
  onFetchPackages,
  onFetchSections,
  onSubmit,
  submitting,
}: CardsContainerProps) {
  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (selectedCardId === null) return;

    const currentIndex = cards.findIndex(c => c.id === selectedCardId);
    if (currentIndex === -1) return;

    if (e.ctrlKey && e.key === 'ArrowUp') {
      e.preventDefault();
      moveCard(currentIndex, currentIndex - 1);
    } else if (e.ctrlKey && e.key === 'ArrowDown') {
      e.preventDefault();
      moveCard(currentIndex, currentIndex + 1);
    } else if (e.key === 'Delete') {
      e.preventDefault();
      deleteCard(currentIndex);
    } else if (e.key === 'Tab') {
      e.preventDefault();
      const nextIndex = e.shiftKey
        ? (currentIndex - 1 + cards.length) % cards.length
        : (currentIndex + 1) % cards.length;
      onSelectedCardIdChange(cards[nextIndex].id);
    }
  }, [selectedCardId, cards]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  function addCard() {
    const usedSourceIps = new Set(cards.map(c => c.source.ip?.normalized.toLowerCase()).filter(Boolean));
    const usedDestIps = new Set(cards.map(c => c.destination.ip?.normalized.toLowerCase()).filter(Boolean));

    // Find first unused IPs
    const firstUnusedSource = sourcePool.find(ip => !usedSourceIps.has(ip.normalized.toLowerCase()));
    const firstUnusedDest = destPool.find(ip => !usedDestIps.has(ip.normalized.toLowerCase()));

    const newCard: RuleCardType = {
      id: Date.now().toString() + Math.random().toString(36).substr(2, 5),
      source: {
        ip: firstUnusedSource || null,
        domain: null,
        package: null,
        section: null,
        position: { type: 'bottom' },
        action: 'accept',
        track: 'log',
      },
      destination: {
        ip: firstUnusedDest || null,
        domain: null,
        package: null,
        section: null,
        position: { type: 'bottom' },
        action: 'accept',
        track: 'log',
      },
      samePackage: false,
    };

    onCardsChange([...cards, newCard]);
    onSelectedCardIdChange(newCard.id);
  }

  function updateCard(index: number, updated: RuleCardType) {
    const newCards = [...cards];
    newCards[index] = updated;
    onCardsChange(newCards);
  }

  function moveCard(fromIndex: number, toIndex: number) {
    if (toIndex < 0 || toIndex >= cards.length) return;

    const newCards = [...cards];
    const [moved] = newCards.splice(fromIndex, 1);
    newCards.splice(toIndex, 0, moved);
    onCardsChange(newCards);
  }

  function deleteCard(index: number) {
    const newCards = cards.filter((_, i) => i !== index);
    onCardsChange(newCards);

    if (newCards.length === 0) {
      onSelectedCardIdChange(null);
    } else if (selectedCardId === cards[index].id) {
      onSelectedCardIdChange(newCards[Math.min(index, newCards.length - 1)].id);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={addCard}
          disabled={sourcePool.length === 0 || destPool.length === 0}
        >
          Add Card
        </Button>
        {cards.length > 0 && (
          <Button
            type="primary"
            size="large"
            onClick={onSubmit}
            loading={submitting}
          >
            Submit Rules
          </Button>
        )}
      </div>

      {cards.length === 0 ? (
        <Empty
          description="No cards yet. Add IPs to pools and click Add Card."
          className={styles.empty}
        />
      ) : (
        <div className={styles.cardsWrapper}>
          <div className={styles.cardsScroll}>
            {cards.map((card, index) => (
              <RuleCard
                key={card.id}
                card={card}
                sourcePool={sourcePool}
                destPool={destPool}
                domains={domains}
                packages={packages}
                sections={sections}
                selected={selectedCardId === card.id}
                onSelect={() => onSelectedCardIdChange(card.id)}
                onUpdate={(updated) => updateCard(index, updated)}
                onMoveUp={() => moveCard(index, index - 1)}
                onMoveDown={() => moveCard(index, index + 1)}
                onDelete={() => deleteCard(index)}
                onFetchPackages={onFetchPackages}
                onFetchSections={onFetchSections}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
