#pragma once

//#include <QButtonGroup>
//#include <QFileSystemWatcher>
//#include <QFrame>
//#include <QLabel>
//#include <QPushButton>
//#include <QStackedWidget>
//#include <QWidget>


#include "selfdrive/ui/qt/widgets/controls.h"

class DPCtrlPanel : public ListWidget {
  Q_OBJECT
public:
  explicit DPCtrlPanel(QWidget *parent);
  void showEvent(QShowEvent *event) override;

public slots:
  void expandToggleDescription(const QString &param);

private:
  Params params;
  std::map<std::string, ParamControl*> toggles;
  ParamSpinBoxControl* auto_shutdown_timer_toggle;
  ParamSpinBoxControl* speed_based_lane_priority_toggle;
//  bool model_specific_toggles_added = false;

  void updateToggles();
};
