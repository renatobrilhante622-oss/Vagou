import 'package:flutter/material.dart';
import 'ui.dart';

class ExecutiveDossier extends StatelessWidget {
  final String name, email;
  final bool premium, verified;
  final int completion;
  const ExecutiveDossier(
      {super.key,
      required this.name,
      required this.email,
      required this.premium,
      required this.verified,
      required this.completion});
  @override
  Widget build(BuildContext context) => Panel(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CompanyAvatar(company: name),
          const SizedBox(width: 12),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(name,
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700)),
                Text(email, style: Theme.of(context).textTheme.bodySmall),
              ])),
          if (premium)
            const Padding(
                padding: EdgeInsets.only(left: 8),
                child: Chip(
                    label: Text('PRO'), visualDensity: VisualDensity.compact)),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          const Expanded(child: Text('Força do perfil')),
          Text('$completion%',
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(width: 8),
          Icon(verified ? Icons.verified : Icons.mark_email_unread_outlined,
              size: 18, color: Brand.teal)
        ]),
        const SizedBox(height: 8),
        LinearProgressIndicator(
            value: completion / 100,
            minHeight: 6,
            borderRadius: BorderRadius.circular(6)),
      ]));
}

class ResumeCard extends StatelessWidget {
  final bool available, busy;
  final VoidCallback onUpload, onView;
  const ResumeCard(
      {super.key,
      required this.available,
      required this.busy,
      required this.onUpload,
      required this.onView});
  @override
  Widget build(BuildContext context) => Panel(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.picture_as_pdf_outlined, color: Brand.teal),
          const SizedBox(width: 10),
          Expanded(
              child: Text(available ? 'Currículo pronto' : 'Currículo PDF',
                  style: const TextStyle(fontWeight: FontWeight.w700)))
        ]),
        const SizedBox(height: 6),
        const Text('PDF privado · até 5 MB e 20 páginas'),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 6, children: [
          OutlinedButton.icon(
              onPressed: busy ? null : onUpload,
              icon: const Icon(Icons.upload_file),
              label:
                  Text(available ? 'Atualizar PDF' : 'Enviar currículo PDF')),
          if (available)
            TextButton.icon(
                onPressed: busy ? null : onView,
                icon: const Icon(Icons.visibility_outlined),
                label: const Text('Visualizar currículo PDF')),
        ]),
      ]));
}
