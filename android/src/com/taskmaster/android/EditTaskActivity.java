package com.taskmaster.android;

import android.app.Activity;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import com.taskmaster.android.model.TaskNode;
import com.taskmaster.android.util.TaskRepository;
import com.taskmaster.android.util.YamlParser;

import java.io.File;
import java.util.*;

public class EditTaskActivity extends Activity {
    private String folderPath;
    private String parentPath;
    private boolean isNew;
    private TaskNode existingTask;

    private EditText titleField, categoryField, tagsField, bodyField;
    private Spinner  statusSpinner;
    private TextView priorityView;
    private int      priority  = 5;
    private boolean  flagState = false;
    private Button   flagBtn;

    private static final String[] STATUS_KEYS   = {"todo","in_progress","blocked","done"};
    private static final String[] STATUS_LABELS = {"Ke zpracovani","Probiha","Blokovano","Hotovo"};

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_edit_task);

        folderPath = getIntent().getStringExtra("folderPath");
        parentPath = getIntent().getStringExtra("parentPath");
        isNew      = getIntent().getBooleanExtra("isNew", true);

        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        setActionBar(toolbar);
        getActionBar().setDisplayHomeAsUpEnabled(true);
        getActionBar().setTitle(isNew ? "Novy ukol" : "Upravit ukol");

        titleField    = (EditText)  findViewById(R.id.titleField);
        categoryField = (EditText)  findViewById(R.id.categoryField);
        tagsField     = (EditText)  findViewById(R.id.tagsField);
        bodyField     = (EditText)  findViewById(R.id.bodyField);
        statusSpinner = (Spinner)   findViewById(R.id.statusSpinner);
        priorityView  = (TextView)  findViewById(R.id.priorityValue);
        flagBtn       = (Button)    findViewById(R.id.flagToggle);

        ArrayAdapter<String> sa = new ArrayAdapter<>(this,
            android.R.layout.simple_spinner_item, STATUS_LABELS);
        sa.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        statusSpinner.setAdapter(sa);

        priority = 5;
        priorityView.setText(String.valueOf(priority));

        ((Button) findViewById(R.id.prioDownBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (priority > 1) { priority--; priorityView.setText(String.valueOf(priority)); }
            }
        });
        ((Button) findViewById(R.id.prioUpBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                if (priority < 10) { priority++; priorityView.setText(String.valueOf(priority)); }
            }
        });

        flagBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                flagState = !flagState;
                flagBtn.setText(flagState ? "Oznaceno" : "Oznacit");
            }
        });

        if (!isNew && folderPath != null) {
            loadExisting();
        } else {
            String inheritStatus   = getIntent().getStringExtra("inheritStatus");
            int    inheritPriority = getIntent().getIntExtra("inheritPriority", 5);
            String inheritCategory = getIntent().getStringExtra("inheritCategory");
            if (inheritStatus != null) setStatusSpinner(inheritStatus);
            priority = inheritPriority;
            priorityView.setText(String.valueOf(priority));
            if (inheritCategory != null) categoryField.setText(inheritCategory);
        }

        ((Button) findViewById(R.id.saveBtn)).setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { save(); }
        });
    }

    private void loadExisting() {
        File folder = new File(folderPath);
        String name = folder.getName();
        File yaml   = new File(folder, name + ".yaml");
        if (!yaml.exists()) return;
        String text = TaskRepository.readFile(yaml);
        if (text == null) return;
        YamlParser meta = YamlParser.parse(text);

        existingTask = new TaskNode();
        existingTask.id = meta.id; existingTask.title = meta.title;
        existingTask.status = meta.status; existingTask.priority = meta.priority;
        existingTask.category = meta.category; existingTask.tags = meta.tags;
        existingTask.created = meta.created; existingTask.modified = meta.modified;
        existingTask.order = meta.order; existingTask.flag = meta.flag;
        existingTask.folderPath = folderPath;

        File mdFile = new File(folder, name + ".md");
        String body = mdFile.exists() ? TaskRepository.readFile(mdFile) : "";
        existingTask.body = body != null ? body : "";

        titleField.setText(existingTask.title);
        categoryField.setText(existingTask.category);
        tagsField.setText(joinList(existingTask.tags, ", "));
        bodyField.setText(existingTask.body);
        setStatusSpinner(existingTask.status);
        priority = existingTask.priority;
        priorityView.setText(String.valueOf(priority));
        flagState = existingTask.flag;
        flagBtn.setText(flagState ? "Oznaceno" : "Oznacit");
    }

    private void setStatusSpinner(String key) {
        for (int i = 0; i < STATUS_KEYS.length; i++) {
            if (STATUS_KEYS[i].equals(key)) { statusSpinner.setSelection(i); return; }
        }
    }

    private String getSelectedStatus() {
        int sel = statusSpinner.getSelectedItemPosition();
        return (sel >= 0 && sel < STATUS_KEYS.length) ? STATUS_KEYS[sel] : "todo";
    }

    private void save() {
        String title = titleField.getText().toString().trim();
        if (title.isEmpty()) {
            Toast.makeText(this, "Nazev nesmi byt prazdny", Toast.LENGTH_SHORT).show(); return;
        }
        String status   = getSelectedStatus();
        String category = categoryField.getText().toString().trim();
        String tagsRaw  = tagsField.getText().toString().trim();
        String body     = bodyField.getText().toString();
        List<String> tags = new ArrayList<>();
        for (String tag : tagsRaw.split(",")) {
            String t = tag.trim(); if (!t.isEmpty()) tags.add(t);
        }

        if (isNew) {
            File parent  = new File(parentPath);
            TaskNode created = TaskRepository.createTask(parent, title, status, priority, category, tags);
            if (created == null) {
                Toast.makeText(this, "Nepodarilo se vytvorit ukol", Toast.LENGTH_SHORT).show(); return;
            }
            created.flag = flagState;
            TaskRepository.saveMeta(created);
            TaskRepository.saveBody(created, body);
        } else {
            existingTask.title    = title;
            existingTask.status   = status;
            existingTask.priority = priority;
            existingTask.category = category;
            existingTask.tags     = tags;
            existingTask.flag     = flagState;
            TaskRepository.saveMeta(existingTask);
            TaskRepository.saveBody(existingTask, body);
        }
        finish();
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) { finish(); return true; }
        return super.onOptionsItemSelected(item);
    }

    private String joinList(List<String> list, String sep) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(sep);
            sb.append(list.get(i));
        }
        return sb.toString();
    }
}
