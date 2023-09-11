#include "selfdrive/ui/qt/offroad/settings_dp.h"

#include "common/params.h"
#include "selfdrive/ui/ui.h"

DPCtrlPanel::DPCtrlPanel(QWidget *parent) : ListWidget(parent) {
  // param, title, desc, icon, confirm
  std::vector<std::tuple<QString, QString, QString>> toggle_defs{
    {
      "",
      QString::fromUtf8("🐉 ") + tr("Ctrl - Overall") + QString::fromUtf8(" 🐉"),
      "",
    },
    {
      "dp_0813",
      tr("Use 0.8.13.1 Driving Model"),
      tr("When enabled, openpilot will use the good old 0.8.13.1 driving model.\nFor safety reason, vision only openpilot longitudinal will be disabled.\nReboot required."),
    },
    {
      "dp_car_dashcam_mode_removal",
      tr("Dashcam Mode Removal"),
      tr("If you see 'Dashcam Mode' while onroad, enable this will force enable openpilot control.\nDashcam Mode usually means your vehicle is not fully supported.\nUSE AT YOUR OWN RISK!\nReboot required."),
    },
    {
      "",
      QString::fromUtf8("🐉 ") + tr("Ctrl - Lateral") + QString::fromUtf8(" 🐉"),
      "",
    },
    {
      "dp_alka",
      tr("Enable ALKA"),
      tr("When enabled, openpilot lateral Control will be always on when ACC MAIN is ON.\nReboot required."),
    },
    {
      "dp_lat_lane_priority_mode",
      tr("Enable Lane Priority Mode"),
      tr("When enabled, openpilot will use lane lines for lateral control, fallback to laneless mode automatically when lane lines probabilities are low."),
    },
    {
      "",
      QString::fromUtf8("🐉 ") + tr("Ctrl - Longitudinal") + QString::fromUtf8(" 🐉"),
      "",
    },
    {
      "dp_long_use_df_tune",
      tr("Enable Dynamic Following"),
      tr("When enabled, openpilot will dynamically adjust following distance based on your \"Driving Personality\" setting.")
    },
    {
      "dp_long_de2e",
      tr("Enable Dynamic End-to-End Longitudinal Control"),
      tr("When enabled, openpilot will dynamically change between End-to-End or ACC mode.\nYour vehicle must support openpilot longitudinal control.")
    },
    {
      "dp_mapd_vision_turn_control",
      tr("Enable Turn Speed Control - Vision"),
      tr("When enabled, openpilot will use path predictions from camera vision to estimate the appropriate speed to drive through turns ahead."),
    },
    {
      "dp_mapd",
      tr("Enable MapD"),
      tr("When enabled, openpilot will display current road name and speed limit on the screen.\nReboot required."),
    },
//    {
//      "SpeedLimitControl",
//      QString::fromUtf8("₯ －　") + tr("MapD - Enable Speed Limit Control"),
//      tr("When enabled, openpilot will use speed limit signs information from map data to automatically adapt cruise speed to road limits.\nReboot required."),
//    },
    {
      "",
      QString::fromUtf8("🐉 ") + tr("Device") + QString::fromUtf8(" 🐉"),
      "",
    },
    {
      "dp_device_disable_temp_check",
      tr("Disable Temp Check"),
      tr("When enabled, openpilot will disable device temperature check.\n**NOTED** An overheated device may result in random shutdowns or lag.\nReboot required."),
    },
    {
      "dp_device_no_ir_ctrl",
      tr("Disable IR"),
      tr("When enabled, openpilot will disable IR completely.\nReboot required."),
    },
    {
      "dp_device_auto_shutdown",
      tr("Enable Auto Shutdown"),
      tr("When enabled, openpilot will shutdown the device automatically.\nReboot required."),
    },
  };

  speed_based_lane_priority_toggle = new ParamSpinBoxControl("dp_lat_lane_priority_mode_speed_based", tr("Only When Drive Above"),
                                                  tr("All Speed - Use Lane Line when available.\n*Number* - Use Lane Line when available and drive speed is above the *number*."),
                                                  "", 0, 120, 1, tr(" kph"), tr("All Speed"));

  std::vector<QString> display_off_mode_texts{tr("Standard"), tr("On-Road"), tr("MAIN"), tr("OP"), tr("Off")};
  ButtonParamControl* display_off_mode_setting = new ButtonParamControl("dp_device_display_off_mode", tr("Display Mode"),
                                          tr("On-Road - When driving, the display will be off (excl. warning).\nMAIN - When ACC MAIN is on, the display will be off (excl. warning).\nOP - When OP is enabled, the display will be off (excl. warning).\nOff - the display will be off completely (incl. warning).\nReboot required."),
                                          "",
                                          display_off_mode_texts);

  std::vector<QString> audible_alert_mode_texts{tr("Standard"), tr("Warning"), tr("Off")};
  ButtonParamControl* audible_alert_mode_setting = new ButtonParamControl("dp_device_audible_alert_mode", tr("Audible Alert Mode"),
                                          tr("Warning - Only emits sound when there is a warning.\nOff - Does not emit any sound at all."),
                                          "",
                                          audible_alert_mode_texts);


  auto_shutdown_timer_toggle = new ParamSpinBoxControl("dp_device_auto_shutdown_in", tr("Auto Shutdown In"), tr("Adjust your shutdown waiting period."), "", 0, 600, 1, tr(" mins"), tr("Immediately"));

  std::vector<QString> dp_long_accel_profile_texts{tr("OP"), tr("ECO"), tr("NOR"), tr("SPT")};
  ButtonParamControl* dp_long_accel_profile_setting = new ButtonParamControl("dp_long_accel_profile", tr("Acceleration Profile"),
                                          tr("OP - Stock tune.\nECO - Eco tune.\nNOR - Normal tune.\nSPT - Sport tune."),
                                          "",
                                          dp_long_accel_profile_texts);
  for (auto &[param, title, desc] : toggle_defs) {
    if (param == "") {
      auto label = new LabelControl(title, "");
      addItem(label);
      continue;
    }
    auto toggle = new ParamControl(param, title, desc, "", this);

    bool locked = params.getBool((param + "Lock").toStdString());
    toggle->setEnabled(!locked);

    addItem(toggle);
    toggles[param.toStdString()] = toggle;

    if (param == "dp_device_auto_shutdown") {
      connect(toggle, &ToggleControl::toggleFlipped, [=]() {
        updateToggles();
      });
      auto_shutdown_timer_toggle->setVisible(false);
      addItem(auto_shutdown_timer_toggle);
      // display off mode
      addItem(display_off_mode_setting);
      // audible alert mode
      addItem(audible_alert_mode_setting);
    }
    if (param == "dp_lat_lane_priority_mode") {
      addItem(speed_based_lane_priority_toggle);
    }
    if (param == "dp_mapd") {
      connect(toggle, &ToggleControl::toggleFlipped, [=]() {
        updateToggles();
      });
    }
    if (param == "dp_mapd_vision_turn_control") {
      // accel profile
      addItem(dp_long_accel_profile_setting);
    }
//    if (param == "SpeedLimitControl") {
//      toggle->setVisible(false);
//    }
  }

  auto cp_bytes = params.get("CarParamsPersistent");
  if (!cp_bytes.empty()) {
    AlignedBuffer aligned_buf;
    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
    cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();

    std::vector<std::tuple<QString, QString, QString>> toyota_toggle_defs{
      {
        "",
        QString::fromUtf8("🐉 ") + tr("Toyota / Lexus") + QString::fromUtf8(" 🐉"),
        "",
      },
      {
        "dp_toyota_sng",
        tr("Enable Stop and Go (SnG) Hack"),
        tr("When enabled, openpilot will stop sending standstill signal when the car is fully stopped.\nONLY WORK ON SOME VEHICLES.\nReboot Required."),
      },
      {
        "dp_toyota_auto_lock",
        tr("Enable Door Auto Locking"),
        tr("When enabled, openpilot will attempt to lock the doors when drive above 10 km/h (6.2 mph).\nReboot Required."),
      },
      {
        "dp_toyota_auto_unlock",
        tr("Enable Door Auto Unlocking"),
        tr("When enabled, openpilot will attempt to unlock the doors when shift to gear P.\nReboot Required."),
      },
    };

    std::vector<std::tuple<QString, QString, QString>> hyundai_toggle_defs{
      {
        "",
        QString::fromUtf8("🐉 ") + tr("Hyundai / Kia / Genesis") + QString::fromUtf8(" 🐉"),
        "",
      },
      {
        "dp_hkg_min_steer_speed_bypass",
        tr("Enable Minimum Steer Speed Bypass"),
        tr("When enabled, openpilot will control the steering to 0 kph/mph.\nMDPS harness may required.\nReboot Required."),
      },
    };

    std::vector<std::tuple<QString, QString, QString>> model_specific_toggle_defs;
    auto car_name = CP.getCarName();
    if (car_name == "toyota") {
      model_specific_toggle_defs = toyota_toggle_defs;
    }
    else if (car_name == "hyundai") {
      model_specific_toggle_defs = hyundai_toggle_defs;
    }

    for (auto& [param, title, desc] : model_specific_toggle_defs) {
      if (param == "") {
        auto label = new LabelControl(title, "");
        addItem(label);
        continue;
      }
      auto toggle = new ParamControl(param, title, desc, "", this);
      bool locked = params.getBool((param + "Lock").toStdString());
      toggle->setEnabled(!locked);
      addItem(toggle);
      toggles[param.toStdString()] = toggle;
    }
  }
  auto resetBtn = new ButtonControl(tr("Reset Configuration"));
  connect(resetBtn, &ButtonControl::clicked, [&]() {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to reset all dp configurations?"), tr("Reset"), this)) {
      params.putBool("dp_reset_conf", true);
    }
  });
  addItem(resetBtn);
}

void DPCtrlPanel::expandToggleDescription(const QString &param) {
  toggles[param.toStdString()]->showDescription();
}

void DPCtrlPanel::showEvent(QShowEvent *event) {
  updateToggles();
}

void DPCtrlPanel::updateToggles() {
  auto_shutdown_timer_toggle->setVisible(params.getBool("dp_device_auto_shutdown"));
  speed_based_lane_priority_toggle->setVisible(params.getBool("dp_lat_lane_priority_mode"));
//  toggles["SpeedLimitControl"]->setVisible(params.getBool("dp_mapd"));
}
